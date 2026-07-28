/**
 * Discord Voice Adapter Implementation for Vencord.
 * 
 * Isolates version-sensitive Discord Webpack module lookups.
 * Uses lazy runtime resolution without static import-time module caching.
 * Does NOT perform DOM scraping, CSS selector queries, or raw REST API calls.
 */

import {
    UserStore as CommonUserStore,
    GuildStore as CommonGuildStore,
    ChannelStore as CommonChannelStore,
    VoiceStateStore as CommonVoiceStateStore,
    MediaEngineStore as CommonMediaEngineStore,
} from "@webpack/common";
import { findByProps } from "@webpack";

import {
    UserSummary,
    GuildSummary,
    VoiceChannelSummary,
    VoiceSettings,
    DiscordVoiceAdapter
} from "./types";

export class VencordDiscordVoiceAdapter implements DiscordVoiceAdapter {

    public get userStore(): any {
        try {
            if (CommonUserStore && typeof CommonUserStore.getCurrentUser === "function") {
                return CommonUserStore;
            }
            if (typeof findByProps === "function") {
                const s = findByProps("getCurrentUser");
                if (s && typeof s.getCurrentUser === "function") return s;
            }
        } catch (e) {}
        return null;
    }

    public get guildStore(): any {
        try {
            if (CommonGuildStore && typeof CommonGuildStore.getGuilds === "function") {
                return CommonGuildStore;
            }
            if (typeof findByProps === "function") {
                const s = findByProps("getGuilds");
                if (s && typeof s.getGuilds === "function") return s;
            }
        } catch (e) {}
        return null;
    }

    public get channelStore(): any {
        try {
            if (CommonChannelStore && typeof CommonChannelStore.getChannel === "function") {
                return CommonChannelStore;
            }
            if (typeof findByProps === "function") {
                const s = findByProps("getChannel", "getChannels");
                if (s && typeof s.getChannel === "function") return s;
            }
        } catch (e) {}
        return null;
    }

    public get voiceStateStore(): any {
        try {
            if (CommonVoiceStateStore && typeof CommonVoiceStateStore.getVoiceChannelId === "function") {
                return CommonVoiceStateStore;
            }
            if (typeof findByProps === "function") {
                const s = findByProps("getVoiceChannelId", "getVoiceStates");
                if (s && typeof s.getVoiceChannelId === "function") return s;
            }
        } catch (e) {}
        return null;
    }

    /** SelectedChannelStore — Discord's own code uses this for getVoiceChannelId() */
    public get selectedChannelStore(): any {
        try {
            if (typeof findByProps === "function") {
                const s = findByProps("getVoiceChannelId", "getChannelId");
                if (s && typeof s.getVoiceChannelId === "function") return s;
                // Fallback: look up by store name via Vencord
                if ((Vencord as any)?.Webpack?.getByStoreName) {
                    const byName = (Vencord as any).Webpack.getByStoreName("SelectedChannelStore");
                    if (byName && typeof byName.getVoiceChannelId === "function") return byName;
                }
            }
        } catch (e) {}
        return null;
    }

    public get mediaEngineStore(): any {
        try {
            if (CommonMediaEngineStore && typeof CommonMediaEngineStore.isSelfMute === "function") {
                return CommonMediaEngineStore;
            }
            if (typeof findByProps === "function") {
                const s = findByProps("isSelfMute", "isSelfDeaf");
                if (s && typeof s.isSelfMute === "function") return s;
            }
        } catch (e) {}
        return null;
    }

    public get voiceChannelActions(): any {
        try {
            if (typeof findByProps === "function") {
                const a = findByProps("selectVoiceChannel", "disconnect");
                if (a) return a;
                const b = findByProps("selectVoiceChannel");
                if (b) return b;
            }
        } catch (e) {}
        return null;
    }

    public get mediaEngineActions(): any {
        try {
            if (typeof findByProps === "function") {
                const a = findByProps("toggleSelfMute", "toggleSelfDeaf");
                if (a) return a;
                const b = findByProps("setSelfMute", "setSelfDeafen");
                if (b) return b;
                const c = findByProps("setLocalVolume");
                if (c) return c;
            }
        } catch (e) {}
        return null;
    }

    public get fluxDispatcher(): any {
        try {
            if (typeof findByProps === "function") {
                const d = findByProps("dispatch", "subscribe");
                if (d && typeof d.dispatch === "function") return d;
            }
        } catch (e) {}
        return null;
    }

    isInitialized(): boolean {
        return !!(this.userStore && this.guildStore && this.channelStore && this.voiceStateStore && this.mediaEngineStore);
    }

    getCurrentUser(): UserSummary | null {
        try {
            const store = this.userStore;
            if (!store || typeof store.getCurrentUser !== "function") {
                return null;
            }

            const user = store.getCurrentUser();
            if (!user || !user.id) return null;

            return {
                id: String(user.id),
                username: String(user.username || ""),
                discriminator: String(user.discriminator || "0"),
                avatar: user.avatar ? String(user.avatar) : null,
                globalName: user.globalName || user.global_name || null,
            };
        } catch (e) {
            console.error("[VeckordAdapter] getCurrentUser error:", e);
            return null;
        }
    }

    getGuilds(): GuildSummary[] {
        try {
            const store = this.guildStore;
            if (!store || typeof store.getGuilds !== "function") {
                return [];
            }

            const rawGuilds = store.getGuilds();
            const results: GuildSummary[] = [];

            if (rawGuilds) {
                const guildList = Array.isArray(rawGuilds) ? rawGuilds : Object.values(rawGuilds);
                for (const g of guildList as any[]) {
                    if (!g || !g.id) continue;
                    results.push({
                        id: String(g.id),
                        name: String(g.name || "Unnamed Guild"),
                        icon: g.icon ? String(g.icon) : null,
                        acronym: g.acronym || String(g.name || "").substring(0, 3).toUpperCase(),
                    });
                }
            }
            return results;
        } catch (e) {
            console.error("[VeckordAdapter] getGuilds error:", e);
            return [];
        }
    }

    getVoiceChannels(guildId: string): VoiceChannelSummary[] {
        try {
            const chStore = this.channelStore;
            let gcStore: any = null;
            try {
                if (typeof findByProps === "function") {
                    gcStore = findByProps("getSelectableVoiceChannels", "getChannels") || findByProps("getMutableGuildChannelsForGuild");
                }
            } catch (e) {}

            const results: VoiceChannelSummary[] = [];
            const rawList: any[] = [];
            const stores = [gcStore, chStore].filter(Boolean);

            for (const store of stores) {
                if (rawList.length > 0) break;

                const methodsToTry = [
                    "getSelectableVoiceChannels",
                    "getMutableGuildChannelsForGuild",
                    "getChannels",
                    "getGuildChannels",
                ];

                for (const mName of methodsToTry) {
                    if (typeof store[mName] === "function") {
                        try {
                            const res = store[mName](guildId);
                            if (res) {
                                if (Array.isArray(res)) {
                                    rawList.push(...res);
                                } else if (typeof res === "object") {
                                    for (const val of Object.values(res)) {
                                        if (Array.isArray(val)) {
                                            rawList.push(...val);
                                        } else if (val && typeof val === "object") {
                                            if ((val as any).channel) rawList.push((val as any).channel);
                                            else rawList.push(val);
                                        }
                                    }
                                }
                            }
                        } catch (e) {}
                    }
                    if (rawList.length > 0) break;
                }
            }

            for (const c of rawList) {
                if (!c || typeof c !== "object") continue;
                const channelType = c.type;
                const isVoice = channelType === 2 || channelType === 13 || (typeof c.isVoice === "function" && c.isVoice());
                if (isVoice) {
                    results.push({
                        id: String(c.id),
                        guildId: String(c.guild_id || guildId),
                        name: String(c.name || "Voice Channel"),
                        position: typeof c.position === "number" ? c.position : 0,
                        userLimit: typeof c.userLimit === "number" ? c.userLimit : 0,
                        memberCount: 0,
                    });
                }
            }
            return results;
        } catch (e) {
            console.error(`[VeckordAdapter] getVoiceChannels error for guild ${guildId}:`, e);
            return [];
        }
    }

    getCurrentVoiceChannel(): VoiceChannelSummary | null {
        try {
            const chStore = this.channelStore;
            const vsStore = this.voiceStateStore;
            const selStore = this.selectedChannelStore;

            // SelectedChannelStore is authoritative for current user's selected voice channel in Discord
            let currentChannelId: string | null = null;
            if (selStore && typeof selStore.getVoiceChannelId === "function") {
                const selId = selStore.getVoiceChannelId();
                if (selId) currentChannelId = String(selId);
            }

            // Fallback 1: VoiceStateStore
            if (!currentChannelId && vsStore && typeof vsStore.getVoiceChannelId === "function") {
                const vsId = vsStore.getVoiceChannelId();
                if (vsId) currentChannelId = String(vsId);
            }

            // Fallback 2: VoiceStateStore user lookup
            if (!currentChannelId && vsStore && typeof vsStore.getVoiceStateForUser === "function") {
                const currentUser = this.getCurrentUser();
                if (currentUser?.id) {
                    const state = vsStore.getVoiceStateForUser(currentUser.id);
                    if (state?.channelId) currentChannelId = String(state.channelId);
                }
            }

            if (!currentChannelId || !chStore) return null;

            const channel = typeof chStore.getChannel === "function" ? chStore.getChannel(currentChannelId) : null;
            if (!channel) return null;

            return {
                id: String(channel.id),
                guildId: String(channel.guild_id || ""),
                name: String(channel.name || "Active Voice Channel"),
                position: channel.position || 0,
                userLimit: channel.userLimit || 0,
                memberCount: 1,
            };
        } catch (e) {
            console.error("[VeckordAdapter] getCurrentVoiceChannel error:", e);
            return null;
        }
    }

    async joinVoiceChannel(channelId: string, guildId?: string): Promise<void> {
        const actions = this.voiceChannelActions;
        if (!actions || (typeof actions.selectVoiceChannel !== "function" && typeof actions.connect !== "function")) {
            throw new Error("Discord VoiceChannelActions is unavailable.");
        }

        if (typeof actions.selectVoiceChannel === "function") {
            actions.selectVoiceChannel(channelId);
        } else if (typeof actions.connect === "function") {
            actions.connect(channelId);
        }
    }

    async leaveVoiceChannel(): Promise<void> {
        const actions = this.voiceChannelActions;
        if (!actions || (typeof actions.selectVoiceChannel !== "function" && typeof actions.disconnect !== "function")) {
            throw new Error("Discord VoiceChannelActions is unavailable.");
        }

        if (typeof actions.selectVoiceChannel === "function") {
            actions.selectVoiceChannel(null);
        } else if (typeof actions.disconnect === "function") {
            actions.disconnect();
        }
    }

    getVoiceSettings(): VoiceSettings {
        try {
            const store = this.mediaEngineStore;
            if (!store) {
                return { isMuted: false, isDeafened: false, isSelfMute: false, isSelfDeaf: false };
            }

            const selfMute = typeof store.isSelfMute === "function" ? Boolean(store.isSelfMute()) : false;
            const selfDeaf = typeof store.isSelfDeaf === "function" ? Boolean(store.isSelfDeaf()) : false;

            return {
                isMuted: selfMute,
                isDeafened: selfDeaf,
                isSelfMute: selfMute,
                isSelfDeaf: selfDeaf,
            };
        } catch (e) {
            console.error("[VeckordAdapter] getVoiceSettings error:", e);
            return { isMuted: false, isDeafened: false, isSelfMute: false, isSelfDeaf: false };
        }
    }

    async setMuted(muted: boolean): Promise<void> {
        const store = this.mediaEngineStore;
        const before = store && typeof store.isSelfMute === "function" ? Boolean(store.isSelfMute()) : false;
        console.log(`[VeckordAdapter] setMuted(${muted}) invoked. Before state: ${before}`);

        if (before === muted) {
            console.log(`[VeckordAdapter] setMuted: state is already ${muted}`);
            return;
        }

        const actions = this.mediaEngineActions;
        const dispatcher = this.fluxDispatcher;

        let invoked = false;
        if (actions && typeof actions.toggleSelfMute === "function") {
            console.log("[VeckordAdapter] Invoking actions.toggleSelfMute()");
            actions.toggleSelfMute();
            invoked = true;
        } else if (actions && typeof actions.setSelfMute === "function") {
            console.log(`[VeckordAdapter] Invoking actions.setSelfMute(${muted})`);
            actions.setSelfMute(muted);
            invoked = true;
        } else if (dispatcher && typeof dispatcher.dispatch === "function") {
            console.log("[VeckordAdapter] Invoking FluxDispatcher.dispatch({ type: 'AUDIO_TOGGLE_SELF_MUTE' })");
            dispatcher.dispatch({ type: "AUDIO_TOGGLE_SELF_MUTE" });
            invoked = true;
        }

        if (!invoked) {
            throw new Error("MUTE_ACTION_UNAVAILABLE: Neither MediaEngineActions nor FluxDispatcher was found.");
        }

        // Poll briefly (up to 1s) to confirm state change
        for (let i = 0; i < 10; i++) {
            await new Promise((r) => setTimeout(r, 100));
            const current = store && typeof store.isSelfMute === "function" ? Boolean(store.isSelfMute()) : false;
            if (current === muted) {
                console.log(`[VeckordAdapter] setMuted SUCCESS confirmed state: ${current}`);
                return;
            }
        }

        const finalState = store && typeof store.isSelfMute === "function" ? Boolean(store.isSelfMute()) : false;
        if (finalState !== muted) {
            throw new Error(`MUTE_STATE_NOT_CONFIRMED: Requested muted=${muted}, but MediaEngineStore.isSelfMute() remains ${finalState}.`);
        }
    }

    async setDeafened(deafened: boolean): Promise<void> {
        const store = this.mediaEngineStore;
        const before = store && typeof store.isSelfDeaf === "function" ? Boolean(store.isSelfDeaf()) : false;
        console.log(`[VeckordAdapter] setDeafened(${deafened}) invoked. Before state: ${before}`);

        if (before === deafened) {
            console.log(`[VeckordAdapter] setDeafened: state is already ${deafened}`);
            return;
        }

        const actions = this.mediaEngineActions;
        const dispatcher = this.fluxDispatcher;

        let invoked = false;
        if (actions && typeof actions.toggleSelfDeaf === "function") {
            console.log("[VeckordAdapter] Invoking actions.toggleSelfDeaf()");
            actions.toggleSelfDeaf();
            invoked = true;
        } else if (actions && typeof actions.setSelfDeafen === "function") {
            console.log(`[VeckordAdapter] Invoking actions.setSelfDeafen(${deafened})`);
            actions.setSelfDeafen(deafened);
            invoked = true;
        } else if (dispatcher && typeof dispatcher.dispatch === "function") {
            console.log("[VeckordAdapter] Invoking FluxDispatcher.dispatch({ type: 'AUDIO_TOGGLE_SELF_DEAF' })");
            dispatcher.dispatch({ type: "AUDIO_TOGGLE_SELF_DEAF" });
            invoked = true;
        }

        if (!invoked) {
            throw new Error("DEAFEN_ACTION_UNAVAILABLE: Neither MediaEngineActions nor FluxDispatcher was found.");
        }

        for (let i = 0; i < 10; i++) {
            await new Promise((r) => setTimeout(r, 100));
            const current = store && typeof store.isSelfDeaf === "function" ? Boolean(store.isSelfDeaf()) : false;
            if (current === deafened) {
                console.log(`[VeckordAdapter] setDeafened SUCCESS confirmed state: ${current}`);
                return;
            }
        }

        const finalState = store && typeof store.isSelfDeaf === "function" ? Boolean(store.isSelfDeaf()) : false;
        if (finalState !== deafened) {
            throw new Error(`DEAFEN_STATE_NOT_CONFIRMED: Requested deafened=${deafened}, but MediaEngineStore.isSelfDeaf() remains ${finalState}.`);
        }
    }
}
