import { access, readFile, rename, writeFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";
import mineflayer from "mineflayer";
import walking from "mineflayer-pathfinder";

const [port, keyPath, specPath] = process.argv.slice(2);
const trial = JSON.parse(await readFile(specPath, "utf8"));
const key = JSON.parse(await readFile(keyPath, "utf8"));
const headers = { "Content-Type": "application/json", Authorization: "Bearer " + key.OPENAI_API_KEY };
if (key.OPENAI_ORG_ID) headers["OpenAI-Organization"] = key.OPENAI_ORG_ID;
const MODEL = "gpt-6-luna";
const SLOT = 960;
const SYSTEM = `Play Minecraft with one partner. Work on shared recipes. A goal counts once when either bot crafts and holds it. Return one compact JSON object.
Allowed actions:
{"act":"collect","id":"bread","left":1234,"right":5678} withdraws all ingredients for that goal from your Minecraft chest.
{"act":"craft","id":"bread"} crafts one batch at your table after collecting the kit.
{"act":"explore","room":"R01"} walks to inspect a clue marker.
{"act":"wait"} waits.
You may additionally include "share":"bread" to send the recipe clue or lock fragment you know for that ID, and "say":"short task message". These go to your partner on an open chat turn. Check progress and divide work when you can. Use the two exact cupboard numbers from the card to collect. Use plain JSON with no Markdown. Keep completed items.`;
const output = (event, detail = {}) => console.log(JSON.stringify({ event, ms: Date.now(), ...detail }));

async function api(suffix, payload) {
    const url = "https://api.openai.com/v1/responses" + suffix;
    try {
        const response = await fetch(url, {
            method: "POST", headers, body: JSON.stringify(payload), signal: AbortSignal.timeout(6500)
        });
        if (response.ok) return await response.json();
        return { failure: response.status === 429 ? "rate_limit" : `http_${response.status}` };
    } catch {
        return { failure: "transport_unknown" };
    }
}

function parse(text) {
    const raw = /\{[^{}]*\}/s.exec(text);
    if (!raw) return null;
    try {
        const action = JSON.parse(raw[0]);
        const name = key => typeof action[key] === "string" ? action[key].toLowerCase().slice(0, 32) : "";
        return { act: ["collect", "craft", "explore", "wait"].includes(action.act) ? action.act : "invalid",
            id: name("id"), room: name("room").toUpperCase(), left: action.left, right: action.right,
            share: name("share"), say: typeof action.say === "string" ? action.say.slice(0, 96) : "" };
    } catch {
        return null;
    }
}

async function decide(input) {
    const basic = { model: MODEL, instructions: SYSTEM, input, reasoning: { effort: "none" } };
    const count = await api("/input_tokens", basic);
    if (count.failure) return { status: `input_${count.failure}`, reserved: 0, action: null };
    if (count.input_tokens > SLOT - 64) throw new Error("Prompt exceeds reserved token slot");
    const result = await api("", { ...basic, store: false, max_output_tokens: SLOT - count.input_tokens });
    if (result.failure) return { status: result.failure, reserved: SLOT, action: null };
    const usage = result.usage;
    if (result.model !== MODEL || usage.input_tokens !== count.input_tokens ||
        usage.total_tokens !== usage.output_tokens + usage.input_tokens || usage.total_tokens > SLOT) {
        throw new Error("Model response violated token accounting");
    }
    const reply = result.output.flatMap(o => o.type === "message" ? o.content : [])
        .filter(o => o.type === "output_text").map(o => o.text).join("");
    return { action: result.status === "completed" ? parse(reply) : null, status: result.status,
        reserved: usage.total_tokens, tokens: [usage.input_tokens, usage.output_tokens] };
}

function inventory(bot) {
    const result = {};
    for (const item of bot.inventory.items()) result[item.name] = (result[item.name] || 0) + item.count;
    return result;
}

async function botFor(name) {
    const bot = mineflayer.createBot({ host: "127.0.0.1", port: Number(port), username: name,
        version: "1.21.1", auth: "offline", viewDistance: "tiny" });
    bot.loadPlugin(walking.pathfinder);
    bot.on("error", error => output("bot_error", { name, kind: error.code || error.name }));
    bot.on("end", reason => output("bot_end", { name, reason }));
    await Promise.race([new Promise((resolve, reject) => {
        bot.once("spawn", resolve);
        bot.once("end", () => reject(new Error("Bot disconnected during spawn")));
    }), sleep(35_000, null, { ref: false }).then(() => { throw new Error("Bot spawn timeout"); })]);
    const moves = new walking.Movements(bot);
    moves.canDig = false;
    moves.allowSprinting = true;
    moves.allowParkour = false;
    bot.pathfinder.setMovements(moves);
    output("ready", { name });
    return bot;
}

function blockAt(bot, xyz) {
    const base = bot.entity.position.floored();
    return bot.blockAt(base.offset(xyz[0] - base.x, xyz[1] - base.y, xyz[2] - base.z));
}

async function walk(bot, xyz) {
    const [x, y, z] = xyz;
    if (bot.entity.position.distanceTo(bot.entity.position.offset(x + 0.5 - bot.entity.position.x,
        y - bot.entity.position.y, z + 0.5 - bot.entity.position.z)) < 1.5) return;
    let timer;
    try {
        await Promise.race([bot.pathfinder.goto(new walking.goals.GoalNear(x, y, z, 1)),
            new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("walk_timeout")), 4200); })]);
    } finally {
        clearTimeout(timer);
        bot.pathfinder.setGoal(null);
    }
}

function ownProgress(a, stock = inventory(a.bot)) {
    return [...a.crafts].filter(id => (stock[id] || 0) > 0).sort();
}

function applyShare(receiver, sender) {
    const id = sender.queue.shift();
    if (id) receiver.known[id] = { ...receiver.known[id], ...sender.known[id] };
    receiver.peer = { goals: ownProgress(sender), intent: sender.intent, message: sender.message };
    return { id: id || null, card: id ? { ...sender.known[id] } : null, ...receiver.peer };
}

function isOpen(seconds) {
    if (trial.schedule === "always") return true;
    if (trial.schedule === "blocks") return (seconds < 60 || (seconds >= 180 && seconds < 240));
    return seconds % 60 < 20;
}

function prompt(agent, round, open) {
    const visible = Object.entries(agent.known).sort(([a], [b]) => a.localeCompare(b))
        .map(([id, { left, right }]) => {
            const kit = Object.entries(trial.cards[id].ingredients);
            const revealed = kit.filter((_, i) => i % 2 === 0 ? left : right)
                .map(([item, count]) => item + "=" + count).join("/");
            return `${id} L=${left || "?"} R=${right || "?"} [${revealed}]`;
        }).join(", ");
    const rooms = trial.mode === "hidden" ? `\nClue rooms still unvisited by you: ${Object.keys(agent.station.rooms).filter(r => !agent.visited.has(r)).join(", ")}.` : "";
    const unknown = trial.mode === "hidden" ? "Four goal cards are available initially. Additional goals are in clue rooms."
        : `Shared goals: ${trial.ids.join(", ")}. You can finish any of them.`;
    return `You are ${agent.alias}. Turn ${round}. Chat ${open ? "open" : "closed"}. ${unknown}\n` +
        `Cards: ${visible}.\nItems you crafted and still hold: ${ownProgress(agent).join(", ") || "none"}.\n` +
        `Kits you already collected: ${[...agent.collected].sort().join(", ") || "none"}.\n` +
        `Last result: ${agent.last || "none"}. Partner state from last open turn: ${JSON.stringify(agent.peer)}.\n` +
        `Work on missing goals. Share missing codes or discovered cards when useful. Avoid work your partner has done.${rooms}`;
}

async function act(a, action, deadline) {
    if (!action || action.act === "invalid") return "invalid_reply";
    if (action.act === "wait") return "wait";
    const { id } = action;
    const bot = a.bot;
    if (Date.now() >= deadline - 1000) return "late_action";
    if (action.act === "explore") {
        if (!a.station.rooms[action.room]) return "no_such_room";
        const room = a.station.rooms[action.room];
        await walk(bot, room.marker);
        const marker = blockAt(bot, room.marker);
        if (Date.now() > deadline) return "late_action";
        if (!marker || !["lime_carpet", "gray_carpet"].includes(marker.name) ||
            bot.entity.position.distanceTo(marker.position.offset(0.5, 0, 0.5)) > 2.8) return "marker_unread";
        a.visited.add(action.room);
        if (!room.id) return "empty_" + action.room;
        const card = trial.cards[room.id];
        a.known[room.id] = { left: card.left, right: card.right };
        a.discoveries.add(room.id);
        return "discovered_" + room.id;
    }
    const card = trial.cards[id];
    if (!card || !a.known[id]) return "unknown_goal";
    if (action.act === "collect") {
        if (a.collected.has(id)) return "kit_already_collected";
        if (Number(action.left) !== card.left || Number(action.right) !== card.right) return "cupboard_locked";
        await walk(bot, a.station.home);
        if (Date.now() >= deadline - 800) return "late_action";
        const chest = blockAt(bot, a.station.chest);
        const window = await bot.openContainer(chest);
        try {
            for (const [item, count] of Object.entries(card.ingredients)) {
                const type = bot.registry.itemsByName[item].id;
                await window.withdraw(type, null, count);
            }
        } finally {
            window.close();
        }
        a.collected.add(id);
        return "collected_" + id;
    }
    if (!a.collected.has(id)) return "collect_kit_first";
    if (a.crafts.has(id)) return "already_crafted";
    await walk(bot, a.station.home);
    if (Date.now() >= deadline - 750) return "late_action";
    const table = blockAt(bot, a.station.table);
    const item = bot.registry.itemsByName[id];
    const recipe = bot.recipesFor(item.id, null, 1, table)[0];
    if (!recipe) return "recipe_unavailable";
    const before = inventory(bot)[id] || 0;
    await bot.craft(recipe, 1, table);
    if (Date.now() > deadline) return "late_craft";
    if ((inventory(bot)[id] || 0) <= before) return "craft_unconfirmed";
    a.crafts.add(id);
    return "crafted_" + id;
}

async function save(data) {
    await writeFile("trace.tmp", JSON.stringify(data) + "\n");
    await rename("trace.tmp", "trace.json");
}

const bots = [];
try {
    for (const name of trial.players) bots.push(await botFor(name));
    for (let attempts = 0; !await access("start.json").then(() => true, () => false); attempts++) {
        if (attempts >= 150) throw new Error("Start gate timed out");
        await sleep(200);
    }
    const clock = JSON.parse(await readFile("start.json", "utf8"));
    const agents = bots.map((bot, i) => {
        const known = {};
        for (const id of trial.seeded) {
            const { left, right } = trial.cards[id];
            known[id] = trial.mode !== "split" ? { left, right } : i === 0 ? { left } : { right };
        }
        return { bot, alias: i === 0 ? "Andy" : "Jill", known, station: trial.stations[i], visited: new Set(),
            discoveries: new Set(), crafts: new Set(), collected: new Set(), queue: [], peer: {}, intent: "",
            message: "", last: "" };
    });
    const rounds = [];
    const deadline = clock.start + trial.duration * 1000;
    let finish = null;
    for (let round = 0; round < trial.duration / trial.step; round++) {
        const at = clock.start + round * trial.step * 1000;
        await sleep(Math.max(0, at - Date.now()));
        if (Date.now() >= deadline - 1100) break;
        const relayAt = Date.now();
        const opened = isOpen(round * trial.step) && isOpen((relayAt - clock.start) / 1000);
        const deliveries = opened ? [applyShare(agents[0], agents[1]), applyShare(agents[1], agents[0])] : [];
        const attempts = await Promise.all(agents.map(async agent => {
            const input = prompt(agent, round + 1, opened);
            const decision = await decide(input);
            let outcome;
            try {
                outcome = await act(agent, decision.action, deadline);
            } catch (error) {
                outcome = "game_error";
                output("game_error", { player: agent.alias, error: error.message.slice(0, 180) });
            }
            const a = decision.action;
            if (a?.share && agent.known[a.share] && !agent.queue.includes(a.share)) agent.queue.push(a.share);
            agent.message = a?.say || "";
            agent.intent = a?.id || a?.room || "";
            agent.last = [a?.act, a?.id || a?.room, outcome].filter(Boolean).join(" ");
            return { player: agent.alias, input, output: decision, outcome, inventory: inventory(agent.bot),
                discoveries: [...agent.discoveries], visits: [...agent.visited], held: ownProgress(agent),
                position: agent.bot.entity?.position.toArray() };
        }));
        rounds.push({ round: round + 1, at, relayAt, end: Date.now(), open: opened, deliveries, attempts });
        const held = new Set(agents.flatMap(a => ownProgress(a))).size;
        if (round === 0 || (round + 1) % 6 === 0) output("progress", { round: round + 1, held });
        if (held === trial.ids.length && Date.now() <= deadline) {
            finish = Date.now();
            break;
        }
    }
    if (finish === null) await sleep(Math.max(0, deadline - Date.now()));
    await sleep(850);
    await save({ model: MODEL, slot_budget: SLOT, start: clock.start, deadline, finish, rounds,
        clients: Object.fromEntries(agents.map(a => [a.alias, inventory(a.bot)])),
        crafted: Object.fromEntries(agents.map(a => [a.alias, [...a.crafts]])) });
    output("ready_to_score");
    await sleep(25_000, null, { ref: false });
} finally {
    for (const bot of bots) bot.quit();
}
