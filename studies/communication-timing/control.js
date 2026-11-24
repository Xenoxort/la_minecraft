// The runner sets a shared start time only after both bots spawn and are positioned.
import { existsSync, readFileSync } from 'node:fs';
import { setTimeout as wait } from 'node:timers/promises';

export const active = process.env.MINECOLLAB_TIMING_STUDY === '1';
export const measured = process.env.MINECOLLAB_TIMING_MEASURED === '1';
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
    if (!clock) return false;
    const elapsed = now - clock.startMs;
    return clock.chatWindowsMs
        ? clock.chatWindowsMs.some(([start, end]) => start <= elapsed && elapsed < end)
        : elapsed >= clock.delayMs;
}

export function phaseInstruction(now = Date.now()) {
    const clock = active && getSchedule();
    if (!clock?.chatWindowsMs) return '';
    const elapsed = now - clock.startMs;
    const next = clock.chatWindowsMs.find(([, end]) => end > elapsed);
    if (canChat(now)) {
        return `Bot chat is open for about ${Math.max(1, Math.ceil((next[1] - elapsed) / 1000))} more seconds. Send any useful information now.\n`;
    }
    return next
        ? `Bot chat is closed. The next window opens in about ${Math.ceil((next[0] - elapsed) / 1000)} seconds. Work independently for now.\n`
        : 'Bot chat is closed for the rest of the episode. Work independently.\n';
}

export function record(event, data, ms = Date.now()) {
    if (active) console.log('STUDY ' + JSON.stringify({ event, ms, ...data }));
}

export async function startEpisode(agent, pauseConversation) {
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
    if (schedule.chatWindowsMs) {
        for (const [open, close] of schedule.chatWindowsMs) {
            for (const [time, chatOpen] of [[open, true], [close, false]]) {
                const at = schedule.startMs + time;
                if (at < Date.now() || at >= schedule.deadlineMs) continue;
                setTimeout(() => {
                    record('phase', { agent: agent.name, chatOpen, scheduledMs: at });
                    if (!chatOpen) pauseConversation();
                }, at - Date.now());
            }
        }
    } else if (schedule.delayMs > 0) {
        setTimeout(() => {
            agent.history.add('system', 'The independent exploration phase is over. Bot chat is now available.');
        }, Math.max(0, schedule.startMs + schedule.delayMs - Date.now()));
    }
    await agent.task.setAgentGoal();
}
