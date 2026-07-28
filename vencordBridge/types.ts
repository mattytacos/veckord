/**
 * Type definitions for Vencord Voice Controller Adapter.
 */

export interface UserSummary {
    id: string;
    username: string;
    discriminator: string;
    avatar: string | null;
    globalName: string | null;
}

export interface GuildSummary {
    id: string;
    name: string;
    icon: string | null;
    acronym: string;
}

export interface VoiceChannelSummary {
    id: string;
    guildId: string;
    name: string;
    position: number;
    userLimit: number;
    memberCount: number;
}

export interface VoiceSettings {
    isMuted: boolean;
    isDeafened: boolean;
    isSelfMute: boolean;
    isSelfDeaf: boolean;
}

export interface RecentChannel {
    guild_id: string;
    channel_id: string;
    guild_name: string;
    channel_name: string;
    last_connected: number;
}

export interface AudioDevice {
    id: string;
    name: string;
}

export interface AudioDeviceSettings {
    inputDevices: AudioDevice[];
    outputDevices: AudioDevice[];
    currentInputId: string;
    currentOutputId: string;
    inputVolume: number;
    outputVolume: number;
}

export interface AudioLevels {
    inputLevel: number;
    outputLevel: number;
    isSpeaking: boolean;
}

export interface DiscordVoiceAdapter {
    /** Identify the current authenticated Discord user */
    getCurrentUser(): UserSummary | null;
    
    /** List all accessible guilds/servers for the current user */
    getGuilds(): GuildSummary[];
    
    /** List voice channels within a specific guild */
    getVoiceChannels(guildId: string): VoiceChannelSummary[];
    
    /** Get summary of the currently selected voice channel (if connected) */
    getCurrentVoiceChannel(): VoiceChannelSummary | null;
    
    /** Join a specific voice channel */
    joinVoiceChannel(channelId: string, guildId?: string): Promise<void>;
    
    /** Leave the current voice channel */
    leaveVoiceChannel(): Promise<void>;
    
    /** Read current mute and deafen state */
    getVoiceSettings(): VoiceSettings;
    
    /** Set self mute state */
    setMuted(muted: boolean): Promise<void>;
    
    /** Set self deafen state */
    setDeafened(deafened: boolean): Promise<void>;

    /** Audio control capabilities */
    getAudioDevices?(): AudioDeviceSettings;
    setAudioDevice?(type: "input" | "output", deviceId: string): Promise<void>;
    getAudioVolumes?(): { inputVolume: number; outputVolume: number };
    setAudioVolume?(type: "input" | "output", volume: number): Promise<void>;
    getAudioLevels?(): AudioLevels;
}


