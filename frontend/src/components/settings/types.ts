export interface SystemSettingsResponse {
  master_url: string;
  host: string;
  port: number;
  debug: boolean;
  database_path: string;
  server_secret_key: string;
  jwt_secret_key: string;
  jwt_algorithm: string;
  jwt_access_token_ttl: number;
  jwt_refresh_token_ttl: number;
  join_token_ttl: number;
  worker_token_ttl: number;
  worker_token_rotation: number;
  heartbeat_interval: number;
  heartbeat_lost_threshold: number;
  heartbeat_stale_threshold: number;
  master_key_path: string;
  cors_origins: string[];
  trusted_proxies: string[];
  enforce_https: boolean;
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  plugins_dir: string;
}
