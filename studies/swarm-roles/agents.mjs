import { access, readFile, rename, writeFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";
import mineflayer from "mineflayer";

const [port, keyPath, specPath] = process.argv.slice(2);
const trial = JSON.parse(await readFile(specPath, "utf8"));
const key = JSON.parse(await readFile(keyPath, "utf8"));
const headers = { "Content-Type": "application/json", Authorization: "Bearer " + key.OPENAI_API_KEY };
if (key.OPENAI_ORG_ID) headers["OpenAI-Organization"] = key.OPENAI_ORG_ID;
const MODEL = "gpt-6-luna";
const SLOT = 960;
const SYSTEM = `Work with three other Minecraft cooks. A shared recipe scores once when any of you crafts and still holds it. Use one kitchen action per turn. Return only JSON:
{"act":"collect|craft|wait","recipe":"exact_item_id","say":"optional short message","why":"optional reason for waiting"}.
Collect withdraws the whole ingredient kit from your chest. Craft uses that kit at your real table. Your kit quantities and the recipes are visible. Keep crafted items. Avoid collecting or crafting items another player already holds. If your team uses assignments, focus on your own outstanding items; you can help elsewhere.
A designated orchestrator may additionally include "assign":{"recipe":"exact_item_id","to":"player name"} in the same JSON object to reassign one unfinished recipe. Move work when it helps and keep cooking when possible. Other cooks can suggest assignments in normal chat. Only the designated orchestrator can update the roster.`;
const emit = (event, data = {}) => console.log(JSON.stringify({ event, ms: Date.now(), ...data }));

async function api(suffix, payload) {
    try {
        const result = await fetch("https://api.openai.com/v1/responses" + suffix, {
            method: "POST", headers, body: JSON.stringify(payload), signal: AbortSignal.timeout(6800)
        });
        if (!result.ok) return { failure: `http_${result.status}` };
        return await result.json();
    } catch {
        return { failure: "transport_unknown" };
    }
}

function parse(text) {
    const from = text.indexOf("{");
    const to = text.lastIndexOf("}");
    if (from < 0 || to < from) return null;
    try {
        const value = JSON.parse(text.slice(from, to + 1));
        if (!value || !["collect", "craft", "wait"].includes(value.act)) return null;
        const field = (x, limit) => typeof x === "string" ? x.trim().slice(0, limit) : "";
        const assign = value.assign;
        return { act: value.act, recipe: field(value.recipe, 40).toLowerCase(),
            say: field(value.say, 72), why: field(value.why, 72),
            assign: assign && typeof assign === "object"
                ? { recipe: field(assign.recipe, 40).toLowerCase(), to: field(assign.to, 24) } : null };
    } catch {
        return null;
    }
}

async function decide(input) {
    const payload = { model: MODEL, instructions: SYSTEM, input, reasoning: { effort: "none" } };
    const count = await api("/input_tokens", payload);
    if (count.failure) return { status: "input_" + count.failure, reserved: 0, action: null };
    if (count.input_tokens > SLOT - 64) throw new Error("Prompt exceeds the reserved token slot");
    const result = await api("", { ...payload, store: false, max_output_tokens: SLOT - count.input_tokens });
    if (result.failure) return { status: result.failure, reserved: SLOT, action: null };
    const usage = result.usage;
    if (result.model !== MODEL || usage.input_tokens !== count.input_tokens ||
        usage.total_tokens !== usage.input_tokens + usage.output_tokens || usage.total_tokens > SLOT) {
        throw new Error("Model response violated token accounting");
    }
    const text = result.output.flatMap(o => o.type === "message" ? o.content : [])
        .filter(o => o.type === "output_text").map(o => o.text).join("");
    return { status: result.status, reserved: usage.total_tokens, tokens: [usage.input_tokens, usage.output_tokens],
        action: result.status === "completed" ? parse(text) : null };
}

function inventory(bot) {
    const stock = {};
    for (const item of bot.inventory.items()) stock[item.name] = (stock[item.name] || 0) + item.count;
    return stock;
}

function at(bot, xyz) {
    const p = bot.entity.position.floored();
    return bot.blockAt(p.offset(xyz[0] - p.x, xyz[1] - p.y, xyz[2] - p.z));
}

async function connect(name) {
    const bot = mineflayer.createBot({ host: "127.0.0.1", port: Number(port), username: name, version: "1.21.1",
        auth: "offline", viewDistance: "tiny" });
    bot.on("error", err => emit("bot_error", { name, kind: err.code || err.name }));
    bot.on("end", reason => emit("bot_end", { name, reason }));
    await Promise.race([new Promise((resolve, reject) => {
        bot.once("spawn", resolve);
        bot.once("end", () => reject(new Error("Bot disconnected during spawn")));
    }), sleep(38_000, null, { ref: false }).then(() => { throw new Error("Bot spawn timed out"); })]);
    emit("ready", { name });
    return bot;
}

function held(a) {
    const stock = inventory(a.bot);
    return [...a.crafts].filter(recipe => (stock[recipe] || 0) > 0).sort();
}

const cards = trial.ids.map(id => {
    const kit = Object.entries(trial.cards[id].ingredients).map(([item, qty]) => item + "=" + qty).join("+");
    return id + ":" + kit;
}).join(", ");

function teamSnapshot(cooks) {
    return Object.fromEntries(cooks.map(a => [a.alias, { held: held(a), intent: a.intent, say: a.say }]));
}

function prompt(a, round, assignments, team) {
    const role = trial.mode === "swarm" ? "You choose work as equal peers. No official assignments."
        : trial.mode === "fixed" ? "Each cook has a fixed recipe assignment."
        : a.alias === trial.leader
            ? "You are the orchestrator. Reassign unfinished work when useful. Your own cooking also counts."
            : `${trial.leader} is the orchestrator. Follow the current assignments and keep working.`;
    return `You are ${a.alias}. Turn ${round}. ${role}\nRecipes: ${cards}\n` +
        `Assignments: ${JSON.stringify(assignments)}\nTeam state from the last turn: ${JSON.stringify(team)}\n` +
        `Your collected kits: ${[...a.kits].sort().join(", ") || "none"}. Your last result: ${a.last}.`;
}

async function act(a, action, deadline) {
    if (!action) return "invalid_reply";
    if (action.act === "wait") return "wait";
    if (Date.now() >= deadline - 850) return "late_action";
    const recipe = action.recipe;
    const card = Object.hasOwn(trial.cards, recipe) ? trial.cards[recipe] : null;
    if (!card) return "unknown_recipe";
    const bot = a.bot;
    if (action.act === "collect") {
        if (a.kits.has(recipe)) return "kit_already_collected";
        const chest = at(bot, a.station.chest);
        if (chest?.name !== "chest") return "station_unavailable";
        const window = await bot.openContainer(chest);
        try {
            for (const [item, qty] of Object.entries(card.ingredients)) {
                const id = bot.registry.itemsByName[item].id;
                await window.withdraw(id, null, qty);
            }
        } finally {
            window.close();
        }
        if (Date.now() > deadline) return "late_action";
        a.kits.add(recipe);
        return "collected";
    }
    if (!a.kits.has(recipe)) return "collect_kit_first";
    if (a.crafts.has(recipe)) return "already_crafted";
    const table = at(bot, a.station.table);
    if (table?.name !== "crafting_table") return "station_unavailable";
    const item = bot.registry.itemsByName[recipe];
    const decoded = bot.recipesFor(item.id, null, 1, table)[0];
    if (!decoded) return "recipe_unavailable";
    const before = inventory(bot)[recipe] || 0;
    await bot.craft(decoded, 1, table);
    if (Date.now() > deadline) return "late_action";
    if ((inventory(bot)[recipe] || 0) <= before) return "craft_unconfirmed";
    a.crafts.add(recipe);
    return "crafted";
}

function revise(assignments, roundActors, names) {
    const leader = roundActors.find(row => row.player === trial.leader);
    const proposed = leader?.decision.action?.assign;
    if (!proposed || trial.mode !== "orchestrator") return null;
    const { recipe, to } = proposed;
    const recipient = names.find(name => name.toLowerCase() === to.toLowerCase());
    if (!Object.hasOwn(assignments, recipe) || !recipient) return { status: "invalid", recipe, to };
    if (roundActors.some(actor => actor.held.includes(recipe))) return { status: "already_done", recipe, to: recipient };
    const from = assignments[recipe];
    if (from === recipient) return { status: "unchanged", recipe, from, to: recipient };
    assignments[recipe] = recipient;
    return { status: "reassigned", recipe, from, to: recipient };
}

async function save(trace) {
    await writeFile("trace.tmp", JSON.stringify(trace) + "\n");
    await rename("trace.tmp", "trace.json");
}

const bots = [];
try {
    for (const name of trial.players) bots.push(await connect(name));
    for (let tick = 0; !await access("start.json").then(() => true, () => false); tick++) {
        if (tick >= 160) throw new Error("Server did not open the start gate");
        await sleep(180);
    }
    const clock = JSON.parse(await readFile("start.json", "utf8"));
    const assignments = { ...trial.initial_owners };
    const cooks = bots.map((bot, i) => ({ bot, alias: trial.aliases[i], station: trial.stations[i], kits: new Set(),
        crafts: new Set(), intent: "", say: "", last: "none" }));
    const rounds = [];
    const deadline = clock.start + trial.duration * 1000;
    let finish = null;
    for (let turn = 0; turn < trial.duration / trial.step; turn++) {
        const due = clock.start + turn * trial.step * 1000;
        await sleep(Math.max(0, due - Date.now()));
        if (Date.now() >= deadline - 1000) break;
        const team = teamSnapshot(cooks);
        const owners = { ...assignments };
        const attempts = await Promise.all(cooks.map(async a => {
            const input = prompt(a, turn + 1, owners, team);
            const decision = await decide(input);
            let outcome;
            try {
                outcome = await act(a, decision.action, deadline);
            } catch (error) {
                outcome = "game_error";
                emit("game_error", { player: a.alias, error: error.message.slice(0, 170) });
            }
            const action = decision.action;
            a.intent = action?.recipe || "";
            a.say = action?.say || "";
            a.last = [action?.act, action?.recipe, outcome].filter(Boolean).join(" ");
            return { player: a.alias, input, decision, outcome, inventory: inventory(a.bot), held: held(a) };
        }));
        const update = revise(assignments, attempts, trial.aliases);
        const goals = new Set(attempts.flatMap(row => row.held)).size;
        rounds.push({ turn: turn + 1, due, sampled_at: Date.now(), team, owners, attempts, update, goals });
        if (turn === 0 || (turn + 1) % 6 === 0) emit("progress", { turn: turn + 1, goals });
        if (goals === trial.ids.length && Date.now() <= deadline) {
            finish = Date.now();
            break;
        }
    }
    if (finish === null) await sleep(Math.max(deadline - Date.now(), 0));
    await sleep(1000);
    await save({ model: MODEL, slot_budget: SLOT, start: clock.start, deadline, finish, rounds,
        clients: Object.fromEntries(cooks.map(a => [a.alias, inventory(a.bot)])),
        crafted: Object.fromEntries(cooks.map(a => [a.alias, [...a.crafts]])) });
    emit("ready_to_score");
    await sleep(28_000, null, { ref: false });
} finally {
    for (const bot of bots) bot.quit();
}
