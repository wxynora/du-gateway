export type EntryScene = {
  name: string;
  code?: string;
  genre?: string;
  difficulty?: string;
};

export type FeedItem = {
  id: string;
  kind: "user" | "system" | "notice" | "loot" | "ai_player";
  text: string;
};

export type WenyouHistoryItem = { role?: string; content?: string; timestamp?: string };

export type WenyouShopItem = {
  id: string;
  name: string;
  kind: string;
  category?: string;
  item_type?: string;
  rarity: string;
  price: number;
  desc: string;
  sealed?: boolean;
  sealed_reason?: string;
};

export type WenyouInventoryItem = {
  uid?: string;
  id?: string;
  name: string;
  kind?: string;
  category?: string;
  rarity?: string;
  effect?: string;
  desc?: string;
  quantity?: number;
  uses_left?: number;
  durability?: number;
  durability_max?: number;
  item_type?: string;
  broken?: boolean;
  temporary?: boolean;
  quest_item?: boolean;
  carry_out?: boolean;
  sigil?: string;
  sealed?: boolean;
  sealed_reason?: string;
  source?: string;
};

export type WenyouCoreAbility = {
  id?: string;
  name?: string;
  desc?: string;
  rarity?: string;
  uses_per_instance?: number;
  tags?: string[];
  source_tags?: string[];
};

export type WenyouPlayerStats = {
  display_name?: string;
  hp?: number;
  hp_max?: number;
  san?: number;
  san_max?: number;
  spi_current?: number;
  spi_max?: number;
  level?: number;
  rank?: string;
  exp?: number;
  str?: number;
  con?: number;
  agi?: number;
  int?: number;
  spi?: number;
  luk?: number;
  vit?: number;
  wis?: number;
  core_ability?: WenyouCoreAbility | null;
  conditions?: string[];
  unspent_attribute_points?: number;
  physical_attack?: number;
  ranged_attack?: number;
  defense?: number;
  mental_resist?: number;
};

export type WenyouPromotionPreview = {
  available?: boolean;
  current_rank?: string;
  target_rank?: string;
  required_level?: number;
  cost?: number;
  attribute_bonus?: number;
  reasons?: string[];
};

export type WenyouGrowthPlayer = {
  attributes?: Record<string, number>;
  soft_cap?: number;
  unspent_attribute_points?: number;
  core_ability?: WenyouCoreAbility | null;
  next_level_exp?: number;
  spi_current?: number;
  spi_max?: number;
  promotion?: WenyouPromotionPreview;
};

export type WenyouGrowthView = {
  attribute_keys?: string[];
  rank_soft_caps?: Record<string, number>;
  players?: Record<string, WenyouGrowthPlayer>;
};

export type WenyouShopView = {
  active?: boolean;
  can_buy?: boolean;
  phase?: string;
  phaseLabel?: string;
  points?: number;
  debts?: number;
  inventory?: WenyouInventoryItem[];
  stats?: {
    phase?: string;
    points?: number;
    player1?: WenyouPlayerStats;
    player2?: WenyouPlayerStats;
    inventory?: WenyouInventoryItem[];
  };
  growth?: WenyouGrowthView | null;
  generatedAt?: string;
  items?: WenyouShopItem[];
  shop_state?: {
    regular?: {
      rotation_id?: string;
      refresh_count?: number;
      refresh_limit?: number;
      refresh_cost?: number;
      items?: WenyouShopItem[];
    };
  };
};

export type WenyouTeamChannelMessage = {
  id?: string;
  sender?: "player1" | "player2" | "system" | string;
  text?: string;
  timestamp?: string;
  consume_turn?: boolean;
};

export type WenyouTeamChannel = {
  status?: string;
  label?: string;
  risk?: string;
  frequency?: string;
  noise?: number;
  blocked?: boolean;
  peer_display_name?: string;
  current_location?: string;
  messages?: WenyouTeamChannelMessage[];
};

export type WenyouTaskPanelItem = string | {
  id?: string;
  title?: string;
  current?: string;
  goal?: string;
  type?: string;
  status?: string;
  progress?: { current?: number; target?: number; mode?: string; text?: string } | string;
  required_clues?: string[];
  related_clues?: string[];
  fail_forward?: string;
  reward_tags?: string[];
};

export type WenyouCluePanelItem = string | {
  id?: string;
  title?: string;
  status?: string;
  verified?: boolean;
  source?: string;
  public_text?: string;
  text?: string;
  related_tasks?: string[];
  leads_to?: string[];
  tags?: string[];
};

export type WenyouPublicMarker = string | {
  id?: string;
  name?: string;
  title?: string;
  status?: string;
  public_status?: string;
  public_text?: string;
  desc?: string;
  blurb?: string;
  danger?: string;
  last_location?: string;
  attitude?: string;
  weakness?: string;
  type?: string;
  tier?: string;
  rank?: string;
  stability?: number;
  stability_max?: number;
  seal_progress?: number;
  seal_target?: number;
  weaknesses?: string[];
  counterplay?: string[];
};

export type WenyouPublicState = {
  scene_summary?: string;
  visible_rules?: string[];
  public_tasks?: WenyouTaskPanelItem[];
  discovered_clues?: WenyouCluePanelItem[];
  known_locations?: WenyouPublicMarker[];
  visible_npcs?: WenyouPublicMarker[];
  visible_monsters?: WenyouPublicMarker[];
  public_threat?: string;
  last_rules_result?: string;
  forced_notice?: string;
};

export type WenyouRulesState = {
  players?: Record<string, WenyouPlayerStats>;
  inventory?: WenyouInventoryItem[];
  threat_clocks?: Array<Record<string, unknown>>;
  last_state_patch?: Record<string, unknown> | null;
};

export type WenyouSessionPanel = {
  gameId?: string;
  phase?: string;
  phase_label?: string;
  framework?: {
    instance_code?: string;
    instance_name?: string;
    instance_genre?: string;
    genre_note?: string;
    difficulty?: string;
    world?: string;
    conflict?: string;
    failure_hint?: string;
    reward_hint?: string;
    tasker_total?: number;
    player_count?: number;
    npc_taskers?: Array<Record<string, unknown>>;
  };
  task?: {
    current?: string;
    failure_hint?: string;
    reward_hint?: string;
    phase?: string;
  };
  stats?: {
    phase?: string;
    points?: number;
    player1?: WenyouPlayerStats;
    player2?: WenyouPlayerStats;
    inventory?: WenyouInventoryItem[];
  };
  wallet?: { points?: number; debts?: number; total_exp?: number } | null;
  growth?: WenyouGrowthView | null;
  settlement?: Record<string, unknown> | null;
  inventory?: WenyouInventoryItem[];
  clues?: string[];
  public_state?: WenyouPublicState;
  public_view?: WenyouPublicState;
  rules_state?: WenyouRulesState;
  team_channel?: WenyouTeamChannel;
  runtime_state?: {
    public_state?: WenyouPublicState;
    rules_state?: WenyouRulesState;
    last_state_patch?: Record<string, unknown> | null;
  };
  clocks?: Array<Record<string, unknown>>;
  last_state_patch?: Record<string, unknown> | null;
  history?: WenyouHistoryItem[];
};

export type StorySegment = {
  id: string;
  kind: "story" | "system" | "actions";
  label?: string;
  text: string;
  options?: StoryActionOption[];
};

export type StoryActionOption = {
  key: string;
  text: string;
  free?: boolean;
};
