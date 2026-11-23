// The runner sets a shared start time only after both bots spawn and are positioned.
import { existsSync, readFileSync } from 'node:fs';
import { setTimeout as wait } from 'node:timers/promises';

export const active = process.env.MINECOLLAB_TIMING_STUDY === '1';
let schedule;

function getSchedule() {
    if (!schedule && existsSync('start.json')) {
        schedule = JSON.parse(readFileSync('start.json', 'utf8'));
    }
    return schedule;
}

export function canChat(now = Date.now()) {
    if (!active) return true;
    const clock = getSchedule();
    return Boolean(clock && now >= clock.startMs + clock.delayMs);
}

export function record(event, data) {
    if (active) console.log('STUDY ' + JSON.stringify({ event, ms: Date.now(), ...data }));
}

export async function startEpisode(agent) {
    record('ready', { agent: agent.name });
    while (!getSchedule()) await wait(100);
    await wait(Math.max(0, schedule.startMs - Date.now()));
    const snapshot = () => {
        const position = agent.bot.entity?.position;
        const inventory = {};
        for (const item of agent.bot.inventory.items()) {
            inventory[item.name] = (inventory[item.name] || 0) + item.count;
        }
        record('state', {
            agent: agent.name,
            position: position ? [position.x, position.y, position.z] : null,
            inventory
        });
    };
    snapshot();
    setInterval(snapshot, 1000);
    if (schedule.delayMs > 0) {
        setTimeout(() => {
            agent.history.add('system', 'The independent exploration phase is over. Bot chat is now available.');
        }, Math.max(0, schedule.startMs + schedule.delayMs - Date.now()));
    }
    await agent.task.setAgentGoal();
}
