import { readFile, access, writeFile, rename } from "node:fs/promises";
import { setTimeout as wait } from "node:timers/promises";
import mineflayer from "mineflayer";

const [trialPath, startPath, worldPort, keyPath, outputPath] = process.argv.slice(2);
const trial = JSON.parse(await readFile(trialPath, "utf8"));
const config = JSON.parse(await readFile(keyPath, "utf8"));
const headers = { "Content-Type": "application/json", Authorization: "Bearer " + config.OPENAI_API_KEY };
if (config.OPENAI_ORG_ID) headers["OpenAI-Organization"] = config.OPENAI_ORG_ID;
const MODEL = "gpt-6-luna";
const SLOT = 960;
const WAVES_PER_PERIOD = 8 / trial.names.length;
const SYSTEM = "You are playing Minecraft Hell's Kitchen as a bot. Your score is the items you actually craft and retain in your own inventory. One action per attempt. Return only JSON: {\"action\":\"take|craft|wait\",\"item\":\"minecraft_item_name\",\"count\":1,\"note\":\"short private reminder\"}. Take withdraws one type of ingredient from your own chest. Craft uses the real ingredients in your inventory at your own table. Craft actions make a single recipe batch. Save your own notes and prioritize filling your assigned goals. Try independently when chat is closed. Do not claim an item you do not hold.";
const API = "https://api.openai.com/v1/responses";
const log = (event, data = {}) => console.log(JSON.stringify({ event, at_ms: Date.now(), ...data }));

async function post(suffix, input) {
    for (let i = 0; i < 3; i++) {
        try {
            const response = await fetch(API + suffix, {
                method: "POST", headers, body: JSON.stringify(input), signal: AbortSignal.timeout(24_000)
            });
            if (response.ok) return await response.json();
            const error = await response.json().catch(() => ({}));
            if ((response.status === 429 || (suffix && [502, 503, 504].includes(response.status))) && i < 2) {
                await wait(300 * 2 ** i);
                continue;
            }
            if (response.status === 400 && error.error?.code === "invalid_prompt") return { unavailable: "rejected" };
            if (response.status === 429 || response.status >= 500) return { unavailable: "provider_unavailable" };
            throw new Error(`Provider HTTP ${response.status} (${error.error?.code || "unknown"})`);
        } catch (error) {
            if (!["TimeoutError", "TypeError", "AbortError"].includes(error.name)) throw error;
            if (!suffix || i === 2) return { unavailable: "transport_unknown" };
            await wait(350 * 2 ** i);
        }
    }
    throw new Error("Missing provider response");
}

function actionFrom(text) {
    const match = /\{[^{}]*\}/s.exec(text);
    if (!match) return null;
    try {
        const a = JSON.parse(match[0]);
        if (!["take", "craft", "wait"].includes(a.action)) return null;
        if (a.action !== "wait" && (typeof a.item !== "string" || !/^[a-z_]+$/.test(a.item))) return null;
        return { action: a.action, item: a.item, count: Number.isInteger(a.count) ? Math.min(64, Math.max(1, a.count)) : 1,
            note: typeof a.note === "string" ? a.note.slice(0, 82) : "" };
    } catch {
        return null;
    }
}

async function decide(input) {
    const request = { model: MODEL, instructions: SYSTEM, input, reasoning: { effort: "none" } };
    const counted = await post("/input_tokens", request);
    if (counted.unavailable) return { action: null, status: "input_" + counted.unavailable, reserved: 0 };
    if (SLOT - counted.input_tokens < 64) throw new Error("Prompt exceeded its token allocation");
    const replied = await post("", { ...request, max_output_tokens: SLOT - counted.input_tokens, store: false });
    if (replied.unavailable) return { action: null, status: replied.unavailable, reserved: SLOT };
    const usage = replied.usage;
    if (replied.model !== MODEL || usage.input_tokens !== counted.input_tokens ||
        usage.total_tokens !== usage.input_tokens + usage.output_tokens || usage.total_tokens > SLOT) {
        throw new Error("Provider response does not match the reserved token budget");
    }
    const text = replied.output.flatMap(o => o.type === "message" ? o.content : [])
        .filter(o => o.type === "output_text").map(o => o.text).join("");
    return { action: replied.status === "completed" ? actionFrom(text) : null, status: replied.status,
        reserved: usage.total_tokens, tokens: { input: usage.input_tokens, output: usage.output_tokens } };
}

function inventory(bot) {
    const counts = {};
    for (const item of bot.inventory.items()) counts[item.name] = (counts[item.name] || 0) + item.count;
    return Object.fromEntries(Object.entries(counts).sort());
}

async function connect(name) {
    const bot = mineflayer.createBot({ host: "127.0.0.1", port: Number(worldPort), username: name,
        version: "1.21.1", auth: "offline", viewDistance: "tiny" });
    bot.on("error", err => log("bot_error", { name, code: err.code ?? err.name }));
    bot.on("end", reason => log("bot_disconnected", { name, reason }));
    bot.on("kicked", () => log("bot_kicked", { name }));
    await Promise.race([new Promise((resolve, reject) => {
        bot.once("spawn", resolve);
        bot.once("end", () => reject(new Error(name + " disconnected before spawn")));
    }), wait(36_000, null, { ref: false }).then(() => { throw new Error(name + " never spawned"); })]);
    log("bot_ready", { name });
    return bot;
}

async function blockAt(bot, pos, expected) {
    for (let i = 0; i < 50; i++) {
        const p = bot.entity.position.offset(...pos.map((v, j) => v - Math.floor(bot.entity.position[["x", "y", "z"][j]]))).floored();
        const block = bot.blockAt(p);
        if (block?.name === expected) return block;
        await wait(120);
    }
    throw new Error(`Private station lacks a loaded ${expected}`);
}

async function execute(agent, action) {
    if (!action) return "missing_action";
    agent.note = action.note;
    const bot = agent.bot;
    if (action.action === "wait") return "wait";
    const kind = bot.registry.itemsByName[action.item];
    if (!kind) return "unknown_item";
    const before = inventory(bot)[action.item] || 0;
    if (action.action === "take") {
        const window = await bot.openContainer(agent.chest);
        try {
            const available = window.containerItems().filter(item => item.type === kind.id).reduce((n, item) => n + item.count, 0);
            if (available < action.count) return "stock_unavailable";
            await window.withdraw(kind.id, null, action.count);
            agent.stock[action.item] -= action.count;
        } finally {
            window.close();
        }
    } else {
        const recipe = bot.recipesFor(kind.id, null, 1, agent.table)[0];
        if (!recipe) return "recipe_or_ingredients_unavailable";
        await bot.craft(recipe, 1, agent.table);
    }
    const gained = (inventory(bot)[action.item] || 0) - before;
    if (gained > 0) {
        if (action.action === "craft") agent.receipts.add(action.item);
        return `gained_${gained}`;
    }
    return "no_inventory_gain";
}

function relay(agents) {
    for (const a of agents) {
        for (const p of agents) {
            if (p === a) continue;
            a.shared[p.name] = { cards: p.cards, recipes_crafted: [...p.receipts].sort() };
        }
    }
}

function compactStock(a) {
    return Object.entries(a.stock).filter(([, count]) => count > 0).map(([item, count]) => `${item}=${count}`).join(" ");
}

function prompt(a, period, step, open) {
    const visible = a.publicCards || [a.cards, ...Object.values(a.shared).map(p => p.cards)];
    const own = visible.filter(p => p.owner === a.name).flatMap(p => p.goals);
    const peers = Object.entries(a.shared).filter(([, p]) => p.recipes_crafted.length)
        .map(([name, p]) => `${name}:${p.recipes_crafted.join(",")}`).join(" ") || "none";
    const visibleCards = visible.map(p => p.owner + " " + p.goals.map(g => g.item + ": " + g.recipe).join("; ")).join("\n");
    return `Bot ${a.name}. Period ${period}/10, attempt ${step + 1}, chat ${open ? "open" : "closed"}.\n` +
        `Your targets: ${own.length ? own.map(g => g.item).join(", ") : "Your recipe card is held by another bot"}\n` +
        `Visible recipe cards:\n${visibleCards}\nOwn inventory: ${JSON.stringify(inventory(a.bot))}\n` +
        `Your local chest: ${compactStock(a)}\nPreviously shared peer crafting receipts: ${peers}\n` +
        `Your previous action result: ${a.last || "none"}. Private note: ${a.note || "none"}.\n` +
        `Use available supplies and real crafting. When all known personal goals are held, wait.`;
}

function adaptiveOpen(period, periods) {
    const used = periods.filter(p => p.open).length;
    if (used === 4) return false;
    if (11 - period === 4 - used) return true;
    if (period === 1) return trial.information === "split";
    if (period < 3 || periods.at(-1).open) return false;
    return periods.at(-1).goals_held <= periods.at(-2).goals_held;
}

const bots = [];
try {
    // Connect in a short stagger so the server can finish initial chunk setup.
    const connections = trial.names.map(async (name, i) => {
        await wait(i * 45);
        const bot = await connect(name);
        bots.push(bot);
        return bot;
    });
    const ordered = await Promise.all(connections);
    for (let retry = 0; ; retry++) {
        if (retry === 120) throw new Error("Server never released the start gate");
        if (await access(startPath).then(() => true, () => false)) break;
        await wait(200);
    }
    const agents = await Promise.all(ordered.map(async (bot, i) => ({
        bot, name: trial.names[i],
        chest: await blockAt(bot, trial.stations[i].chest, "chest"),
        table: await blockAt(bot, trial.stations[i].table, "crafting_table"),
        stock: { ...trial.stations[i].supplies }, cards: trial.cards[(i + 1) % ordered.length],
        publicCards: trial.information === "public" ? trial.cards : null,
        receipts: new Set(), shared: {}, note: "", last: ""
    })));
    const started = Date.now();
    const periods = [];
    for (let period = 1; period <= 10; period++) {
        const open = trial.schedule === "G" ? adaptiveOpen(period, periods) : trial.windows.includes(period);
        const attempts = [];
        for (let step = 0; step < WAVES_PER_PERIOD; step++) {
            if (open) relay(agents);
            const rows = await Promise.all(agents.map(async a => {
                const visible = JSON.parse(JSON.stringify(a.shared));
                const input = prompt(a, period, step, open);
                const decision = await decide(input);
                let outcome;
                try {
                    outcome = await execute(a, decision.action);
                } catch (err) {
                    outcome = "game_action_error";
                    log("action_error", { name: a.name, error: err.message.slice(0, 180) });
                }
                a.last = decision.action ? [decision.action.action, decision.action.item, outcome].filter(Boolean).join(" ") : outcome;
                return { name: a.name, step, visible, input, ...decision, outcome, inventory: inventory(a.bot) };
            }));
            attempts.push(...rows);
        }
        const goals_held = agents.reduce((n, a, i) => n + trial.cards[i].goals.filter(g => inventory(a.bot)[g.item] > 0).length, 0);
        const state = { period, open, goals_held, attempts };
        periods.push(state);
        log("period", { period, open, goals_held });
        const tmp = outputPath + ".tmp";
        await writeFile(tmp, JSON.stringify({ model: MODEL, token_budget: 10 * 8 * SLOT, wall_seconds: (Date.now() - started) / 1000,
            periods, inventories: Object.fromEntries(agents.map(a => [a.name, inventory(a.bot)])) }) + "\n");
        await rename(tmp, outputPath);
    }
    log("ready_to_score", { agents: agents.length });
    // Hold the connections until the server samples the terminal inventories.
    await wait(45_000, null, { ref: false });
} finally {
    for (const bot of bots) bot.quit();
}
