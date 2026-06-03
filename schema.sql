-- WARNING: This schema is for context only and is not meant to be run.
-- Table order and constraints may not be valid for execution.

CREATE TABLE public.tracked_players (
  player_tag character varying NOT NULL,
  CONSTRAINT tracked_players_pkey PRIMARY KEY (player_tag)
);
CREATE TABLE public.leagues (
  league_id bigint NOT NULL,
  league_name character varying NOT NULL,
  emoji character varying,
  attack_limit integer,
  CONSTRAINT leagues_pkey PRIMARY KEY (league_id)
);
CREATE TABLE public.ranked_battles (
  battle_id bigint NOT NULL DEFAULT nextval('ranked_battles_battle_id_seq'::regclass),
  player_tag character varying NOT NULL,
  recorded_at timestamp without time zone NOT NULL,
  is_attack boolean NOT NULL,
  opponent_player_tag character varying NOT NULL,
  stars integer NOT NULL,
  destruction_percentage integer NOT NULL,
  army_share_code text,
  battle_hash character varying NOT NULL UNIQUE,
  league_season_id bigint,
  CONSTRAINT ranked_battles_pkey PRIMARY KEY (battle_id),
  CONSTRAINT ranked_battles_player_tag_fkey FOREIGN KEY (player_tag) REFERENCES public.tracked_players(player_tag)
);
CREATE TABLE public.league_history (
  player_tag character varying NOT NULL,
  league_season_id bigint NOT NULL,
  league_id bigint,
  placement integer,
  league_trophies integer NOT NULL,
  attack_wins integer NOT NULL,
  attack_losses integer NOT NULL,
  attack_stars integer NOT NULL,
  defense_wins integer NOT NULL,
  defense_losses integer NOT NULL,
  defense_stars integer NOT NULL,
  max_battles integer NOT NULL,
  CONSTRAINT league_history_pkey PRIMARY KEY (player_tag, league_season_id),
  CONSTRAINT league_history_player_tag_fkey FOREIGN KEY (player_tag) REFERENCES public.tracked_players(player_tag),
  CONSTRAINT league_history_league_id_fkey FOREIGN KEY (league_id) REFERENCES public.leagues(league_id)
);
CREATE TABLE public.wars (
  war_id bigint NOT NULL DEFAULT nextval('wars_war_id_seq'::regclass),
  clan_tag character varying NOT NULL,
  opponent_clan_tag character varying NOT NULL,
  team_size integer NOT NULL,
  attacks_per_member integer NOT NULL,
  preparation_start_time timestamp without time zone NOT NULL,
  start_time timestamp without time zone NOT NULL,
  end_time timestamp without time zone NOT NULL,
  war_state character varying NOT NULL,
  created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
  war_type character varying NOT NULL DEFAULT 'regular'::character varying,
  CONSTRAINT wars_pkey PRIMARY KEY (war_id)
);
CREATE TABLE public.war_attacks (
  attack_id bigint NOT NULL DEFAULT nextval('war_attacks_attack_id_seq'::regclass),
  war_id bigint NOT NULL,
  attacker_tag character varying NOT NULL,
  defender_tag character varying NOT NULL,
  stars integer NOT NULL,
  destruction_percentage integer NOT NULL,
  duration_seconds integer,
  attack_order integer NOT NULL,
  CONSTRAINT war_attacks_pkey PRIMARY KEY (attack_id),
  CONSTRAINT war_attacks_war_id_fkey FOREIGN KEY (war_id) REFERENCES public.wars(war_id),
  CONSTRAINT war_attacks_attacker_tag_fkey FOREIGN KEY (attacker_tag) REFERENCES public.tracked_players(player_tag)
);
CREATE TABLE public.league_group_rankings (
  player_tag character varying NOT NULL,
  league_group_tag character varying NOT NULL,
  league_season_id bigint NOT NULL,
  tournament_rank integer NOT NULL,
  CONSTRAINT league_group_rankings_pkey PRIMARY KEY (player_tag, league_group_tag, league_season_id),
  CONSTRAINT league_group_rankings_player_tag_fkey FOREIGN KEY (player_tag) REFERENCES public.tracked_players(player_tag)
);
CREATE TABLE public.player_season_cache (
  player_tag character varying NOT NULL,
  league_season_id bigint NOT NULL,
  updated_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT player_season_cache_pkey PRIMARY KEY (player_tag),
  CONSTRAINT player_season_cache_player_tag_fkey FOREIGN KEY (player_tag) REFERENCES public.tracked_players(player_tag)
);