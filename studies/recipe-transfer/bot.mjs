import { readFile, rename, writeFile } from "node:fs/promises";
import { setTimeout as sleep } from "node:timers/promises";
import mineflayer from "mineflayer";

const [port, keyPath, specPath] = process.argv.slice(2);
const trial = JSON.parse(await readFile(specPath, "utf8"));
const key = JSON.parse(await readFile(keyPath, "utf8"));
const headers = { "Content-Type": "application/json", Authorization: "Bearer " + key.OPENAI_API_KEY };
if (key.OPENAI_ORG_ID) headers["OpenAI-Organization"] = key.OPENAI_ORG_ID;
const SLOT = 2500;
const SYSTEM = `Complete four hidden Minecraft food orders. An order uses one ingredient from each shelf A, B, C. Shelf ranks are numbered 1 to 5 in the order shown. For each order the clue gives the sum of the three correct ranks. Each test uses one chosen ingredient per shelf at the Minecraft crafting table. You may test a combination even if it does not fit the clue. The feedback says how many choices were correct in their own shelf, without naming which ones. A 3/3 test makes the food and delivers the order automatically. All ingredients remain available until the deadline. You get one test per turn.
Reply as a single JSON object: {"order":"o1","ranks":[1,2,3],"note":"optional brief action rationale"}. Choose an unfinished order. All three ranks are integers between 1 and 5. Finish as many as you can.`;
const event = (name, data = {}) => console.log(JSON.stringify({ event: name, ms: Date.now(), ...data }));

function getPrompt(turn, history, done) {
    const { shelves, orders } = trial.public;
    const lines = shelves.map((shelf, i) => String.fromCharCode(65 + i) + ": " +
        shelf.map((ingredient, j) => `${j + 1}=${ingredient}`).join(" "));
    const clues = Object.entries(orders).map(([id, clue]) =>
        `${id} makes ${clue.food}. Rank sum ${clue.sum}. ${done.has(id) ? "Delivered." : "Open."}`);
    const evidence = history.filter(row => row.action && row.matches !== null)
        .map(row => `${row.action.order} [${row.action.ranks.join(",")}] => ${row.matches}/3`);
    return [`Turn ${turn} of ${trial.duration / trial.step}.`, ...lines, ...clues,
        trial.knowledge ? "Transferred notes:\n" + trial.knowledge : "Transferred notes: none.",
        "Your observed tests: " + (evidence.join("; ") || "none")].join("\n");
}

async function post(suffix, body, until) {
    const remaining = until - Date.now();
    if (remaining <= 0) return { failure: "decision_deadline" };
    try {
        const result = await fetch("https://api.openai.com/v1/responses" + suffix, {
            method: "POST", headers, body: JSON.stringify(body), signal: AbortSignal.timeout(remaining),
        });
        if (!result.ok) return { failure: "http_" + result.status };
        return await result.json();
    } catch (error) {
        return { failure: error.name === "TimeoutError" ? "timeout" : "transport_error" };
    }
}

function parse(text) {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start < 0 || end < start) return null;
    try {
        const raw = JSON.parse(text.slice(start, end + 1));
        if (typeof raw?.order !== "string" || !Array.isArray(raw.ranks) || raw.ranks.length !== 3 ||
            raw.ranks.some(n => !Number.isInteger(n) || n < 1 || n > 5)) return null;
        return { order: raw.order.trim().toLowerCase().slice(0, 12), ranks: raw.ranks,
            note: typeof raw.note === "string" ? raw.note.trim().slice(0, 160) : "" };
    } catch {
        return null;
    }
}

async function decide(input, until) {
    const request = { model: trial.model, instructions: SYSTEM, input, reasoning: { effort: "low" } };
    const count = await post("/input_tokens", request, until);
    if (count.failure) return { status: "input_" + count.failure, reserved: 0, action: null };
    if (!Number.isInteger(count.input_tokens) || count.input_tokens > SLOT - 128) {
        throw new Error("Prompt exceeded the matched slot budget");
    }
    const response = await post("", { ...request, store: false, max_output_tokens: SLOT - count.input_tokens }, until);
    if (response.failure) return { status: response.failure, reserved: SLOT, action: null };
    const usage = response.usage;
    if (response.model !== trial.model || usage.input_tokens !== count.input_tokens ||
        usage.total_tokens !== usage.input_tokens + usage.output_tokens || usage.total_tokens > SLOT) {
        throw new Error("Provider token accounting mismatch");
    }
    const text = response.output.flatMap(item => item.type === "message" ? item.content : [])
        .filter(item => item.type === "output_text").map(item => item.text).join("");
    return { status: response.status, reserved: usage.total_tokens,
        tokens: { input: usage.input_tokens, output: usage.output_tokens,
            cached: usage.input_tokens_details?.cached_tokens ?? 0 },
        action: response.status === "completed" ? parse(text) : null };
}

function scripted(turn) {
    const ids = Object.keys(trial.orders);
    const id = ids[Math.max(0, turn - 3)];
    const correct = trial.orders[id].ingredients.map((ingredient, i) => trial.public.shelves[i].indexOf(ingredient) + 1);
    const ranks = correct.map((n, i) => turn === 1 || (turn === 2 && i === 0) ? n % 5 + 1 : n);
    return { status: "scripted", reserved: 0, action: { order: id, ranks, note: "" } };
}

function blockAt(bot, [x, y, z]) {
    const p = bot.entity.position.floored();
    return bot.blockAt(p.offset(x - p.x, y - p.y, z - p.z));
}

async function putOne(bot, window, name, slot) {
    const id = bot.registry.itemsByName[name].id;
    const supplies = window.findInventoryItem(id, null);
    if (!supplies) throw new Error("Missing stocked item " + name);
    await bot.clickWindow(supplies.slot, 0, 0);
    await bot.clickWindow(slot, 1, 0);
    if (window.selectedItem) await bot.clickWindow(supplies.slot, 0, 0);
}

async function tryRecipe(bot, order, ingredients, matches) {
    const block = blockAt(bot, trial.positions.table);
    if (block?.name !== "crafting_table") throw new Error("Crafting table is missing");
    const table = await bot.openBlock(block);
    let output;
    try {
        if (!table.type.startsWith("minecraft:crafting")) throw new Error("Invalid crafting window");
        const grid = [order.ticket, ...ingredients];
        for (let i = 0; i < grid.length; i++) await putOne(bot, table, grid[i], i + 1);
        await bot.waitForTicks(4);
        output = table.slots[0]?.name ?? null;
        if (output !== (matches === 3 ? order.food : null)) {
            throw new Error(`Server craft grid returned ${output} for a ${matches}/3 test of ${order.food}`);
        }
        if (output) await bot.putAway(0);
    } finally {
        table.close();
    }
    if (output) {
        const outbox = blockAt(bot, trial.positions.outbox);
        if (outbox?.name !== "chest") throw new Error("Delivery chest is missing");
        const window = await bot.openContainer(outbox);
        try {
            await window.deposit(bot.registry.itemsByName[output].id, null, 1);
        } finally {
            window.close();
        }
    }
    return output;
}

async function gate() {
    const until = Date.now() + 45_000;
    while (Date.now() < until) {
        try {
            return JSON.parse(await readFile("start.json", "utf8")).start;
        } catch (error) {
            if (error.code !== "ENOENT") throw error;
        }
        await sleep(100);
    }
    throw new Error("The start gate did not open");
}

const bot = mineflayer.createBot({ host: "127.0.0.1", port: Number(port), username: trial.player,
    version: "1.21.1", auth: "offline", viewDistance: "tiny" });
bot.on("error", error => event("bot_error", { type: error.code || error.name }));
bot.on("end", reason => event("bot_end", { reason }));
try {
    await Promise.race([new Promise((resolve, reject) => {
        bot.once("spawn", resolve);
        bot.once("end", () => reject(new Error("Disconnected before spawn")));
    }), sleep(37_000, null, { ref: false }).then(() => { throw new Error("Spawn timed out"); })]);
    event("ready", { player: trial.player });
    const start = await gate();
    const deadline = start + trial.duration * 1000;
    const history = [];
    const done = new Set();
    let finish = null;
    for (let turn = 1; turn <= trial.duration / trial.step; turn++) {
        const due = start + (turn - 1) * trial.step * 1000;
        await sleep(Math.max(0, due - Date.now()));
        const input = getPrompt(turn, history, done);
        const decision = trial.scripted ? scripted(turn) : await decide(input, due + 13500);
        const action = decision.action;
        const row = { turn, due, input, decision, action, matches: null, craft: null, at: null };
        if (!action || !Object.hasOwn(trial.orders, action.order)) row.outcome = "invalid_reply";
        else if (done.has(action.order)) row.outcome = "already_delivered";
        else if (Date.now() >= Math.min(due + trial.step * 1000, deadline) - 1700) row.outcome = "action_window_closed";
        else {
            const order = trial.orders[action.order];
            row.ingredients = action.ranks.map((rank, i) => trial.public.shelves[i][rank - 1]);
            row.matches = row.ingredients.filter((ingredient, i) => order.ingredients[i] === ingredient).length;
            row.craft = await Promise.race([tryRecipe(bot, order, row.ingredients, row.matches),
                sleep(3800, null, { ref: false }).then(() => { throw new Error("Crafting transaction timed out"); })]);
            row.at = Date.now();
            if (row.at >= deadline) throw new Error("Craft crossed deadline");
            row.outcome = row.craft ? "delivered" : "tested";
            if (row.craft) done.add(action.order);
        }
        history.push(row);
        if (turn % 4 === 0 || trial.scripted || done.size === Object.keys(trial.orders).length) {
            event("progress", { turn, delivered: done.size, status: decision.status, outcome: row.outcome });
        }
        if (done.size === Object.keys(trial.orders).length) {
            finish = row.at;
            break;
        }
    }
    if (!finish) await sleep(Math.max(0, deadline - Date.now()));
    await writeFile("trace.tmp", JSON.stringify({ model: trial.model, slot: SLOT, start, deadline, finish,
        done: [...done].sort(), history }) + "\n");
    await rename("trace.tmp", "trace.json");
    event("ready_to_score");
    await sleep(26_000, null, { ref: false });
} finally {
    bot.quit();
}
