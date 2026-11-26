import { readFile, rename, writeFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";
import mineflayer from "mineflayer";

const [port, keyPath, specPath] = process.argv.slice(2);
const trial = JSON.parse(await readFile(specPath, "utf8"));
const secret = JSON.parse(await readFile(keyPath, "utf8"));
const headers = { "Content-Type": "application/json", Authorization: "Bearer " + secret.OPENAI_API_KEY };
if (secret.OPENAI_ORG_ID) headers["OpenAI-Organization"] = secret.OPENAI_ORG_ID;
const MODEL = "gpt-6-luna";
const SLOT = 1450;
const SYSTEM = `You are one of four cooks in a Minecraft kitchen. Finish all ten team orders quickly. You receive the same live board as everyone.
Use exactly one action each turn: "prep" moves your numbered ingredient batch from your supply to the order's shared chest; "assemble" takes all staged ingredients, crafts the order at your own bench, and puts the food in the order chest; "wait" does nothing. Only the listed source cook may prep that batch. Only the current owner with an open bench may assemble, and only after every batch is marked + on the board.
Respond in JSON only: {"act":"prep|assemble|wait","job":"o1.2 for prep or o1 for assemble","say":"optional brief team message","route":{"order":"o1","to":"cook name"}}. Omit route if you have no change. You may route and prep or assemble in the same turn where allowed. At most one route is accepted per turn. A route only changes a ready, undelivered order and applies next turn. Bench closures affect assembly only. Keep preparing whenever possible. A prep and an assembly always refer to the board at the start of the turn.`;

const names = Object.keys(trial.players);
const orders = Object.entries(trial.orders);
const emit = (event, data = {}) => console.log(JSON.stringify({ event, ms: Date.now(), ...data }));
const newState = () => Object.fromEntries(orders.map(([id, order]) => [id, { owner: order.owner, parts: [], done: false }]));
const ready = (row, order) => row.parts.length === Object.keys(order.parts).length;
const closed = (turn) => trial.environment === "outage" &&
    (turn - 1) * trial.step >= trial.close && (turn - 1) * trial.step < trial.reopen ? trial.affected : null;

async function gate(path, until) {
    while (Date.now() < until) {
        try {
            return JSON.parse(await readFile(path, "utf8"));
        } catch (error) {
            if (error.code !== "ENOENT") throw error;
        }
        await sleep(65);
    }
    throw new Error("Missing server gate " + path);
}

async function api(suffix, payload, until) {
    const limit = until - Date.now();
    if (limit <= 0) return { failure: "decision_deadline" };
    try {
        const response = await fetch("https://api.openai.com/v1/responses" + suffix, {
            method: "POST", headers, body: JSON.stringify(payload), signal: AbortSignal.timeout(limit)
        });
        if (!response.ok) return { failure: `http_${response.status}` };
        return await response.json();
    } catch (error) {
        return { failure: error.name === "TimeoutError" ? "timeout" : "transport_unknown" };
    }
}

function parse(text) {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start < 0 || end < start) return null;
    try {
        const result = JSON.parse(text.slice(start, end + 1));
        if (!result || !["prep", "assemble", "wait"].includes(result.act)) return null;
        const field = (value, limit) => typeof value === "string" ? value.trim().slice(0, limit) : "";
        return { act: result.act, job: field(result.job, 10).toLowerCase(), say: field(result.say, 78),
            route: result.route && typeof result.route === "object"
                ? { order: field(result.route.order, 8).toLowerCase(), to: field(result.route.to, 16) } : null };
    } catch {
        return null;
    }
}

async function decide(input, until) {
    const body = { model: MODEL, instructions: SYSTEM, input, reasoning: { effort: "none" } };
    const count = await api("/input_tokens", body, until);
    if (count.failure) return { status: "input_" + count.failure, reserved: 0, action: null };
    if (!Number.isInteger(count.input_tokens) || count.input_tokens > SLOT - 80) {
        throw new Error("Prompt exceeds the reserved token slot");
    }
    const response = await api("", { ...body, store: false, max_output_tokens: SLOT - count.input_tokens }, until);
    if (response.failure) return { status: response.failure, reserved: SLOT, action: null };
    const usage = response.usage;
    if (response.model !== MODEL || usage.input_tokens !== count.input_tokens ||
        usage.total_tokens !== usage.input_tokens + usage.output_tokens || usage.total_tokens > SLOT) {
        throw new Error("Unexpected provider or model token accounting");
    }
    const text = response.output.flatMap(item => item.type === "message" ? item.content : [])
        .filter(item => item.type === "output_text").map(item => item.text).join("");
    return { status: response.status, reserved: usage.total_tokens, tokens: [usage.input_tokens, usage.output_tokens],
        action: response.status === "completed" ? parse(text) : null };
}

async function connect(name) {
    const bot = mineflayer.createBot({ host: "127.0.0.1", port: Number(port), username: name, version: "1.21.1",
        auth: "offline", viewDistance: "tiny" });
    bot.on("error", error => emit("bot_error", { name, kind: error.code || error.name }));
    bot.on("end", reason => emit("bot_end", { name, reason }));
    await Promise.race([new Promise((resolve, reject) => {
        bot.once("spawn", resolve);
        bot.once("end", () => reject(new Error("Bot disconnected during spawn")));
    }), sleep(38_000, null, { ref: false }).then(() => { throw new Error("Bot spawn timed out"); })]);
    emit("ready", { name });
    return bot;
}

function at(bot, [x, y, z]) {
    const p = bot.entity.position.floored();
    return bot.blockAt(p.offset(x - p.x, y - p.y, z - p.z));
}

function count(items) {
    const stock = {};
    for (const item of items) stock[item.name] = (stock[item.name] || 0) + item.count;
    return stock;
}

async function changeChest(bot, coords, work) {
    const chest = at(bot, coords);
    if (chest?.name !== "chest") throw new Error("Expected a real Minecraft chest at " + coords.join(","));
    const window = await bot.openContainer(chest);
    try {
        return await work(window);
    } finally {
        window.close();
    }
}

async function move(bot, coords, method, items) {
    return changeChest(bot, coords, async window => {
        for (const [item, quantity] of Object.entries(items)) {
            await window[method](bot.registry.itemsByName[item].id, null, quantity);
        }
        return count(window.containerItems());
    });
}

function ingredients(order) {
    const stock = {};
    for (const part of Object.values(order.parts)) {
        for (const [id, n] of Object.entries(part.items)) stock[id] = (stock[id] || 0) + n;
    }
    return stock;
}

function prompt(name, turn, state, messages, unavailable) {
    const roles = {
        fixed: "The owner column is fixed. Arrange handoffs with chat.",
        peer: "You are equal peers. Claim any ready order for yourself if another owner is blocked or busy.",
        leader: name === trial.leader
            ? "You are the coordinator. Direct ready orders to available cooks. You can cook and route in the same turn."
            : `${trial.leader} can redirect orders. You can suggest changes in chat and follow the board.`,
        dispatch: "A shared dispatch rule routes ready work away from the closed bench. Follow the board.",
    };
    const orderBoard = orders.map(([id, order]) => {
        const row = state[id];
        if (row.done) return `${id} ${order.item} x${order.quantity} delivered`;
        const parts = Object.entries(order.parts)
            .map(([part, data]) => `${part}:${data.cook}${row.parts.includes(part) ? "+" : ""}`).join(" ");
        return `${id} ${order.item} x${order.quantity} owner=${row.owner} batches=${parts}`;
    }).join("\n");
    return `You are ${name}. Turn ${turn}. ${roles[trial.mode]}
Closed assembly bench: ${unavailable ?? "none"}. "+" means that ingredient batch is staged.
${orderBoard}
Previous actions and open chat: ${messages.join(" | ") || "none"}`;
}

function scriptedAction(name, state, unavailable) {
    const meal = orders.find(([id, order]) => !state[id].done && state[id].owner === name &&
        ready(state[id], order) && name !== unavailable);
    const prep = orders.flatMap(([id, order]) => Object.entries(order.parts)
        .filter(([part, source]) => source.cook === name && !state[id].parts.includes(part))
        .map(([part]) => `${id}.${part}`))[0];
    const atRisk = orders.find(([id, order]) => !state[id].done && ready(state[id], order) &&
        state[id].owner === unavailable);
    const route = atRisk && name !== unavailable && (trial.mode === "peer" || trial.leader === name)
        ? { order: atRisk[0], to: name } : null;
    const action = meal ? { act: "assemble", job: meal[0] } : prep ? { act: "prep", job: prep } : { act: "wait", job: "" };
    return { status: "scripted", reserved: 0, action: { ...action, say: "", route } };
}

function validateAction(name, action, state, unavailable) {
    if (!action) return "invalid_reply";
    if (action.act === "wait") return "wait";
    const [id, partId, extra] = action.job.split(".");
    if (!Object.hasOwn(trial.orders, id)) return "unknown_order";
    const order = trial.orders[id];
    const row = state[id];
    if (row.done) return "already_delivered";
    if (action.act === "prep") {
        const part = order.parts[partId];
        if (!Object.hasOwn(order.parts, partId) || extra !== undefined) return "unknown_batch";
        if (part.cook !== name) return "wrong_source";
        if (row.parts.includes(partId)) return "already_staged";
    } else {
        if (partId !== undefined) return "expected_order";
        if (row.owner !== name) return "wrong_owner";
        if (unavailable === name) return "bench_closed";
        if (!ready(row, order)) return "ingredients_pending";
    }
    return null;
}

async function perform(bot, name, action, state, start) {
    const [id, part] = action.job.split(".");
    const order = trial.orders[id];
    const bench = trial.benches[name];
    if (action.act === "prep") {
        const items = order.parts[part].items;
        await move(bot, bench.supply, "withdraw", items);
        const chest = await move(bot, order.chest, "deposit", items);
        state[id].parts.push(part);
        state[id].parts.sort();
        return { outcome: "staged", chest, at: Date.now() - start };
    }
    const table = at(bot, bench.table);
    if (table?.name !== "crafting_table") throw new Error("Expected bench verified open on server");
    const item = bot.registry.itemsByName[order.item];
    const before = count(bot.inventory.items())[order.item] || 0;
    const empty = await move(bot, order.chest, "withdraw", ingredients(order));
    if (Object.keys(empty).length) throw new Error("Order chest still contains ingredients after withdrawal");
    const recipe = bot.recipesFor(item.id, null, order.crafts, table)[0];
    if (!recipe || recipe.result.count * order.crafts !== order.quantity) throw new Error("Recipe mismatch " + id);
    for (let craft = 0; craft < order.crafts; craft++) {
        const current = bot.recipesFor(item.id, null, 1, table)[0];
        if (!current) throw new Error("Still needed ingredients for " + id);
        try {
            await bot.craft(current, 1, table);
        } catch (error) {
            throw new Error(`Unable to craft ${id} (${order.item}, batch ${craft + 1}): ${error.message}`);
        }
        await bot.waitForTicks(2);
    }
    if ((count(bot.inventory.items())[order.item] || 0) - before !== order.quantity) {
        throw new Error("Output quantity mismatch " + id);
    }
    const chest = await move(bot, order.chest, "deposit", { [order.item]: order.quantity });
    state[id].done = true;
    return { outcome: "delivered", chest, at: Date.now() - start };
}

function reassign(attempts, state, before, unavailable, turn, readyTimes) {
    const offset = (trial.seed + turn) % names.length;
    const ordered = attempts.slice(offset).concat(attempts.slice(0, offset));
    const candidates = ordered.filter(row => row.decision.action?.route)
        .map(row => ({ who: row.name, ...row.decision.action.route }));
    if (trial.mode === "dispatch" && unavailable) {
        const free = ordered.find(row => row.name !== unavailable
            && !orders.some(([id, order]) => before[id].owner === row.name && !before[id].done && ready(before[id], order)));
        const blocked = orders.filter(([id, order]) => before[id].owner === unavailable
            && !before[id].done && ready(before[id], order))
            .sort(([a], [b]) => readyTimes.get(a) - readyTimes.get(b))[0];
        if (free && blocked) candidates.push({ who: "rule", order: blocked[0], to: free.name });
    }
    let accepted = false;
    return candidates.map(attempt => {
        const { who, order, to } = attempt;
        const recipient = names.find(name => name.toLowerCase() === to.toLowerCase());
        const row = Object.hasOwn(state, order) ? state[order] : null;
        let status;
        if (!row || !recipient) status = "invalid";
        else if (trial.mode === "fixed" || (trial.mode === "leader" && who !== trial.leader)
            || (trial.mode === "peer" && who !== recipient) || (trial.mode === "dispatch" && who !== "rule")) {
            status = "forbidden";
        } else if (row.done || !ready(before[order], trial.orders[order])) status = "not_ready";
        else if (row.owner === recipient) status = "unchanged";
        else if (accepted) status = "turn_limit";
        else {
            status = "routed";
            accepted = true;
        }
        const from = row?.owner ?? null;
        if (status === "routed") row.owner = recipient;
        return { who, order, to: recipient ?? to, from, status };
    });
}

async function observedPhase(bots, label, due) {
    const signal = await gate(label + ".json", due + 2500);
    const table = trial.benches[trial.affected].table;
    const bot = bots[trial.affected];
    while (Date.now() < due + 2800) {
        if (at(bot, table)?.name === signal.block) return signal;
        await sleep(70);
    }
    throw new Error("Bot did not observe real assembly phase " + label);
}

async function writeTrace(data) {
    await writeFile("trace.tmp", JSON.stringify(data) + "\n");
    await rename("trace.tmp", "trace.json");
}

const bots = {};
try {
    for (const [name, player] of Object.entries(trial.players)) bots[name] = await connect(player);
    const { start } = await gate("start.json", Date.now() + 40_000);
    const deadline = start + trial.duration * 1000;
    const state = newState();
    const turnLog = [];
    const readyTimes = new Map();
    let messages = [];
    let finish = null;
    for (let turn = 1; turn <= trial.duration / trial.step; turn++) {
        const elapsed = (turn - 1) * trial.step;
        const due = start + elapsed * 1000;
        await sleep(Math.max(0, due - Date.now()));
        const phase = elapsed === trial.close ? await observedPhase(bots, "close", due)
            : elapsed === trial.reopen ? await observedPhase(bots, "reopen", due) : null;
        const unavailable = closed(turn);
        const before = structuredClone(state);
        const attempts = await Promise.all(names.map(async name => {
            const input = prompt(name, turn, before, messages, unavailable);
            const decision = trial.scripted ? scriptedAction(name, before, unavailable) : await decide(input, due + 7900);
            const action = decision.action;
            const outcome = validateAction(name, action, before, unavailable);
            return { name, input, decision, outcome };
        }));
        const byOrder = new Map();
        for (const row of attempts.filter(row => !row.outcome)) {
            const order = row.decision.action.job.split(".")[0];
            if (!byOrder.has(order)) byOrder.set(order, []);
            byOrder.get(order).push(row);
        }
        // Mineflayer's inventory transactions against one chest are serialized.
        await Promise.all([...byOrder.values()].map(async rows => {
            for (const row of rows) {
                if (Date.now() >= Math.min(due + trial.step * 1000, deadline) - 1300) {
                    row.outcome = "action_window_closed";
                    continue;
                }
                row.started = Date.now() - start;
                const result = await Promise.race([perform(bots[row.name], row.name, row.decision.action, state, start),
                    sleep(5200, null, { ref: false }).then(() => { throw new Error("Minecraft transaction timed out"); })]);
                Object.assign(row, result);
                if (start + row.at >= deadline) throw new Error("Physical action crossed the deadline");
            }
        }));
        for (const row of attempts.filter(row => row.outcome === "staged").sort((a, b) => a.at - b.at)) {
            const order = row.decision.action.job.split(".")[0];
            if (ready(state[order], trial.orders[order])) readyTimes.set(order, row.at);
        }
        const routes = reassign(attempts, state, before, unavailable, turn, readyTimes);
        messages = attempts.map(row => {
            const action = row.decision.action;
            return `${row.name} ${action?.act ?? "none"} ${action?.job ?? ""} ${row.outcome} ${action?.say ?? ""}`.trim();
        });
        const done = orders.filter(([id]) => state[id].done).map(([id]) => id);
        turnLog.push({ turn, due, phase, unavailable, before, attempts, routes, done });
        if (turn % 5 === 0 || done.length === orders.length) emit("progress", { turn, delivered: done.length });
        if (trial.scripted) emit("probe_step", { turn, actions: attempts.map(row => [row.name, row.decision.action.job, row.outcome]) });
        if (done.length === orders.length) {
            finish = start + Math.max(...attempts.filter(row => row.outcome === "delivered").map(row => row.at));
            break;
        }
    }
    if (!finish) await sleep(Math.max(0, deadline - Date.now()));
    await writeTrace({ model: trial.scripted ? "scripted" : MODEL, slot: SLOT, start, deadline, finish,
        done: orders.filter(([id]) => state[id].done).map(([id]) => id), turns: turnLog });
    emit("ready_to_score");
    await sleep(27_000, null, { ref: false });
} finally {
    for (const bot of Object.values(bots)) bot.quit();
}
