#!/usr/bin/env bash
set -euo pipefail

REPO_OWNER="${REPO_OWNER:-yukkcat}"
REPO_NAME="${REPO_NAME:-chatgpt2api}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/chatgpt2api}"
PORT="${CHATGPT2API_PORT:-${PORT:-3000}}"
THREAD_TOKENS="${CHATGPT2API_THREAD_TOKENS:-${THREAD_TOKENS:-80}}"
MODE="${MODE:-}"
WITH_WARP="${WITH_WARP:-0}"
AUTH_KEY="${CHATGPT2API_AUTH_KEY:-${AUTH_KEY:-}}"
DATABASE_URL="${DATABASE_URL:-}"
INSTALL_LANG="${INSTALL_LANG:-}"
CHATGPT2API_IMAGE="${CHATGPT2API_IMAGE:-}"

UI_DEV="/dev/tty"
if [[ ! -r "${UI_DEV}" ]]; then
  UI_DEV="/dev/stdin"
fi

usage() {
  printf '%s\n\n' "$(text usage_title)"
  printf '%s\n' "$(text usage_usage)"
  cat <<'EOF'
  bash deploy/install.sh
  curl -fsSL https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/deploy/install.sh | sudo bash
EOF

  printf '\n%s\n' "$(text usage_env)"
  cat <<'EOF'
  BRANCH=main
  INSTALL_DIR=/opt/chatgpt2api
  PORT=3000
  CHATGPT2API_THREAD_TOKENS=80
  MODE=docker|python
  WITH_WARP=0|1
  AUTH_KEY=your-auth-key
  DATABASE_URL=postgresql://...
  INSTALL_LANG=zh|en
  CHATGPT2API_IMAGE=ghcr.io/yukkcat/chatgpt2api:latest
EOF

  printf '\n%s\n' "$(text usage_flags)"
  cat <<'EOF'
  --mode docker|python
  --port 3000
  --thread-tokens 80
  --install-dir /opt/chatgpt2api
  --branch main
  --auth-key your-auth-key
  --database-url postgresql://...
  --with-warp
  --without-warp
  --repo-owner yukkcat
  --repo-name chatgpt2api
  -h, --help
EOF
}

ui_print() {
  printf '%s' "$*" >"${UI_DEV}"
}

ui_println() {
  printf '%s\n' "$*" >"${UI_DEV}"
}

is_en() {
  [[ "${INSTALL_LANG}" =~ ^([Ee][Nn]|[Ee]nglish)$ ]]
}

normalize_language() {
  case "${INSTALL_LANG}" in
    en|EN|english|English|英文) INSTALL_LANG="en" ;;
    *) INSTALL_LANG="zh" ;;
  esac
}

choose_language() {
  if [[ -n "${INSTALL_LANG}" ]]; then
    normalize_language
    return
  fi

  local answer=""
  ui_println "界面语言 / Language"
  ui_println "  1) 中文（默认）"
  ui_println "  2) English"
  answer="$(prompt_input "请选择 / Select" "1")"
  case "${answer}" in
    2|en|EN|english|English) INSTALL_LANG="en" ;;
    *) INSTALL_LANG="zh" ;;
  esac
  normalize_language
}

text() {
  local key="$1"
  if is_en; then
    case "${key}" in
      usage_title) printf 'ChatGPT2API installer' ;;
      usage_usage) printf 'Usage:' ;;
      usage_env) printf 'Environment overrides:' ;;
      usage_flags) printf 'Flags:' ;;
      prefix_error) printf 'ERROR' ;;
      prefix_info) printf 'INFO' ;;
      prefix_warn) printf 'WARN' ;;
      prefix_done) printf 'OK' ;;
      err_missing_cmd) printf 'Missing command' ;;
      err_unknown_arg) printf 'Unknown argument' ;;
      err_mode) printf 'MODE must be docker or python.' ;;
      err_port) printf 'PORT must be a number.' ;;
      err_thread_tokens) printf 'CHATGPT2API_THREAD_TOKENS must be a positive number.' ;;
      err_not_git) printf 'exists but is not a git repository.' ;;
      err_compose) printf 'docker compose plugin not found. Please install Docker Compose v2 first.' ;;
      info_update) printf 'Updating' ;;
      info_clone) printf 'Cloning' ;;
      info_start_docker) printf 'Starting Docker service...' ;;
      info_install_uv) printf 'uv not found, installing...' ;;
      warn_no_npm) printf 'npm not found, skipping frontend build. Existing web_dist will be used if present.' ;;
      info_build_vue) printf 'Building Vue console...' ;;
      info_install_py) printf 'Installing Python dependencies...' ;;
      info_start_app) printf 'Starting ChatGPT2API on' ;;
      prompt_mode) printf 'Run mode: docker or python' ;;
      prompt_port) printf 'Web/API port' ;;
      prompt_thread_tokens) printf 'Backend thread tokens' ;;
      prompt_dir) printf 'Install directory' ;;
      prompt_branch) printf 'Git branch or tag' ;;
      prompt_auth) printf 'Admin auth key' ;;
      prompt_warp) printf 'Enable WARP / Privoxy / FlareSolverr compose' ;;
      done_ready) printf 'ChatGPT2API is ready' ;;
      done_auth) printf 'Admin auth key' ;;
      *) printf '%s' "${key}" ;;
    esac
    return
  fi

  case "${key}" in
    err_thread_tokens) printf 'CHATGPT2API_THREAD_TOKENS 必须是正整数。' ;;
    prompt_thread_tokens) printf '后端线程池容量' ;;
    usage_title) printf 'ChatGPT2API 安装脚本' ;;
    usage_usage) printf '用法：' ;;
    usage_env) printf '可用环境变量：' ;;
    usage_flags) printf '可用参数：' ;;
    prefix_error) printf '错误' ;;
    prefix_info) printf '信息' ;;
    prefix_warn) printf '警告' ;;
    prefix_done) printf '完成' ;;
    err_missing_cmd) printf '缺少命令' ;;
    err_unknown_arg) printf '未知参数' ;;
    err_mode) printf '运行模式只能是 docker 或 python。' ;;
    err_port) printf '端口必须是数字。' ;;
    err_not_git) printf '已存在，但不是 Git 仓库。' ;;
    err_compose) printf '未找到 docker compose 插件，请先安装 Docker Compose v2。' ;;
    info_update) printf '正在更新' ;;
    info_clone) printf '正在克隆' ;;
    info_start_docker) printf '正在启动 Docker 服务...' ;;
    info_install_uv) printf '未找到 uv，正在安装...' ;;
    warn_no_npm) printf '未找到 npm，跳过前端构建；如果已有 web_dist，将继续使用现有文件。' ;;
    info_build_vue) printf '正在构建 Vue 控制台...' ;;
    info_install_py) printf '正在安装 Python 依赖...' ;;
    info_start_app) printf '正在启动 ChatGPT2API' ;;
    prompt_mode) printf '运行模式：docker 或 python' ;;
    prompt_port) printf 'Web/API 端口' ;;
    prompt_dir) printf '安装目录' ;;
    prompt_branch) printf 'Git 分支或标签' ;;
    prompt_auth) printf '管理员登录密钥' ;;
    prompt_warp) printf '启用 WARP / Privoxy / FlareSolverr 清障编排' ;;
    done_ready) printf 'ChatGPT2API 已就绪' ;;
    done_auth) printf '管理员登录密钥' ;;
    *) printf '%s' "${key}" ;;
  esac
}

prompt_input() {
  local label="$1"
  local default="${2-}"
  local answer=""

  if [[ -n "${default}" ]]; then
    ui_print "${label} [${default}]: "
  else
    ui_print "${label}: "
  fi

  IFS= read -r answer <"${UI_DEV}" || true
  if [[ -z "${answer}" ]]; then
    answer="${default}"
  fi
  printf '%s' "${answer}"
}

confirm() {
  local label="$1"
  local default="${2:-N}"
  local default_choice="1"
  local answer=""

  if [[ "${default}" =~ ^([Yy]|1|true|TRUE|yes|YES)$ ]]; then
    default_choice="2"
  fi

  ui_println "${label}"
  if is_en; then
    ui_println "  1) No"
    ui_println "  2) Yes"
    answer="$(prompt_input "Select" "${default_choice}")"
  else
    ui_println "  1) 否"
    ui_println "  2) 是"
    answer="$(prompt_input "请选择" "${default_choice}")"
  fi

  case "${answer}" in
    2|y|Y|yes|YES|true|TRUE) return 0 ;;
    *) return 1 ;;
  esac
}

normalize_mode_choice() {
  local value="${1:-}"
  value="${value,,}"
  value="${value//[[:space:]]/}"
  case "${value}" in
    1|d|docker) printf 'docker' ;;
    2|p|py|python) printf 'python' ;;
    *) return 1 ;;
  esac
}


prompt_mode_choice() {
  local default="${1:-docker}"
  local normalized=""
  local answer=""
  normalized="$(normalize_mode_choice "${default}")" || normalized="docker"
  local default_choice="1"
  [[ "${normalized}" == "python" ]] && default_choice="2"

  while true; do
    if is_en; then
      ui_println "Run mode"
      ui_println "  1) Docker container (recommended)"
      ui_println "  2) Python source mode"
      answer="$(prompt_input "Select" "${default_choice}")"
    else
      ui_println "运行模式"
      ui_println "  1) Docker 容器（推荐）"
      ui_println "  2) Python 源码运行"
      answer="$(prompt_input "请选择" "${default_choice}")"
    fi
    normalized="$(normalize_mode_choice "${answer}")" && { printf '%s' "${normalized}"; return; }
    ui_println "[$(text prefix_error)] $(text err_mode)"
  done
}



need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[$(text prefix_error)] $(text err_missing_cmd): $1" >&2
    exit 1
  fi
}

generate_auth_key() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
    return
  fi
  if [[ -r /proc/sys/kernel/random/uuid ]]; then
    tr -d '-' </proc/sys/kernel/random/uuid
    return
  fi
  date +%s%N
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      --mode)
        MODE="${2:-}"
        shift 2
        ;;
      --port)
        PORT="${2:-}"
        shift 2
        ;;
      --thread-tokens)
        THREAD_TOKENS="${2:-}"
        shift 2
        ;;
      --install-dir)
        INSTALL_DIR="${2:-}"
        shift 2
        ;;
      --branch)
        BRANCH="${2:-}"
        shift 2
        ;;
      --auth-key)
        AUTH_KEY="${2:-}"
        shift 2
        ;;
      --database-url)
        DATABASE_URL="${2:-}"
        shift 2
        ;;
      --with-warp)
        WITH_WARP="1"
        shift
        ;;
      --without-warp)
        WITH_WARP="0"
        shift
        ;;
      --repo-owner)
        REPO_OWNER="${2:-}"
        shift 2
        ;;
      --repo-name)
        REPO_NAME="${2:-}"
        shift 2
        ;;
      *)
        echo "[$(text prefix_error)] $(text err_unknown_arg): $1" >&2
        usage >&2
        exit 1
        ;;
    esac
  done
}

validate_inputs() {
  local normalized=""

  normalized="$(normalize_mode_choice "${MODE}")" || { echo "[$(text prefix_error)] $(text err_mode)" >&2; exit 1; }
  MODE="${normalized}"

  if [[ -z "${PORT}" || ! "${PORT}" =~ ^[0-9]+$ ]]; then
    echo "[$(text prefix_error)] $(text err_port)" >&2
    exit 1
  fi

  if [[ -z "${THREAD_TOKENS}" || ! "${THREAD_TOKENS}" =~ ^[0-9]+$ || "${THREAD_TOKENS}" -lt 1 ]]; then
    echo "[$(text prefix_error)] $(text err_thread_tokens)" >&2
    exit 1
  fi


}

repo_url() {
  printf 'https://github.com/%s/%s.git' "${REPO_OWNER}" "${REPO_NAME}"
}

default_image() {
  if [[ -n "${CHATGPT2API_IMAGE}" ]]; then
    printf '%s' "${CHATGPT2API_IMAGE}"
    return
  fi

  if [[ "${BRANCH}" =~ ^v?[0-9] ]]; then
    printf 'ghcr.io/%s/%s:%s' "${REPO_OWNER}" "${REPO_NAME}" "${BRANCH}"
    return
  fi

  printf 'ghcr.io/%s/%s:latest' "${REPO_OWNER}" "${REPO_NAME}"
}

raw_url() {
  printf 'https://raw.githubusercontent.com/%s/%s/%s/%s' "${REPO_OWNER}" "${REPO_NAME}" "${BRANCH}" "$1"
}

download_file() {
  local source_path="$1"
  local target_path="${INSTALL_DIR}/${source_path}"

  mkdir -p "$(dirname "${target_path}")"
  curl -fsSL "$(raw_url "${source_path}")" -o "${target_path}"
}

download_optional_file() {
  local source_path="$1"
  download_file "${source_path}" || true
}

json_escape() {
  local value="${1-}"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '%s' "${value}"
}

write_default_config_json() {
  local config_file="${INSTALL_DIR}/config.json"
  local tmp_file="${config_file}.tmp"

  if [[ -f "${config_file}" ]]; then
    return
  fi
  if [[ -e "${config_file}" ]]; then
    echo "[$(text prefix_error)] ${config_file} exists but is not a regular file." >&2
    exit 1
  fi

  cat >"${tmp_file}" <<EOF
{
  "auth-key": "$(json_escape "${AUTH_KEY}")"
}
EOF

  mv "${tmp_file}" "${config_file}"
  chmod 600 "${config_file}" || true
}

prepare_docker_bundle() {
  need_cmd curl

  mkdir -p "${INSTALL_DIR}"
  download_file "docker-compose.yml"
  if [[ "${WITH_WARP}" == "1" ]]; then
    download_file "docker-compose.warp.yml"
    download_file "scripts/init_proxy_config.py"
    download_file "scripts/privoxy-warp.conf"
  fi
}

prepare_repo() {
  need_cmd git

  if [[ -d "${INSTALL_DIR}/.git" ]]; then
    ui_println "[$(text prefix_info)] $(text info_update) ${INSTALL_DIR}"
    (cd "${INSTALL_DIR}" && git fetch --tags origin)
    (cd "${INSTALL_DIR}" && git checkout "${BRANCH}" >/dev/null 2>&1) || (cd "${INSTALL_DIR}" && git checkout -b "${BRANCH}" "origin/${BRANCH}")
    if (cd "${INSTALL_DIR}" && git ls-remote --exit-code --heads origin "${BRANCH}" >/dev/null 2>&1); then
      (cd "${INSTALL_DIR}" && git pull --ff-only origin "${BRANCH}")
    fi
    return
  fi

  if [[ -e "${INSTALL_DIR}" && -n "$(find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 2>/dev/null | head -n 1)" ]]; then
    echo "[$(text prefix_error)] ${INSTALL_DIR} $(text err_not_git)" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${INSTALL_DIR}")"
  ui_println "[$(text prefix_info)] $(text info_clone) $(repo_url) -> ${INSTALL_DIR}"
  git clone --branch "${BRANCH}" --depth 1 "$(repo_url)" "${INSTALL_DIR}"
}

write_env_file() {
  local env_file="${INSTALL_DIR}/.env"
  local tmp_file="${env_file}.tmp"

  cat >"${tmp_file}" <<EOF
CHATGPT2API_AUTH_KEY=${AUTH_KEY}
CHATGPT2API_PORT=${PORT}
CHATGPT2API_THREAD_TOKENS=${THREAD_TOKENS}
CHATGPT2API_IMAGE=$(default_image)
CHATGPT2API_BASE_URL=

DATABASE_URL=${DATABASE_URL}


WARP_SOCKS_PORT=40000
PRIVOXY_PORT=40080
FLARESOLVERR_PORT=8191
FLARESOLVERR_LOG_LEVEL=info
TZ=Asia/Shanghai
EOF

  mv "${tmp_file}" "${env_file}"
  chmod 600 "${env_file}" || true
}

run_docker() {
  need_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "[$(text prefix_error)] $(text err_compose)" >&2
    exit 1
  fi

  local compose_args=(-f docker-compose.yml)
  if [[ "${WITH_WARP}" == "1" ]]; then
    compose_args=(-f docker-compose.warp.yml)
  fi

  ui_println "[$(text prefix_info)] $(text info_start_docker)"
  (cd "${INSTALL_DIR}" && docker compose "${compose_args[@]}" pull)
  (cd "${INSTALL_DIR}" && docker compose "${compose_args[@]}" up -d)
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  need_cmd curl
  ui_println "[$(text prefix_info)] $(text info_install_uv)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
  need_cmd uv
}

build_frontend() {
  if ! command -v npm >/dev/null 2>&1; then
    ui_println "[$(text prefix_warn)] $(text warn_no_npm)"
    return
  fi

  ui_println "[$(text prefix_info)] $(text info_build_vue)"
  (cd "${INSTALL_DIR}/web-vue" && npm ci && npm run build)
  rm -rf "${INSTALL_DIR}/web_dist"
  mkdir -p "${INSTALL_DIR}/web_dist"
  cp -R "${INSTALL_DIR}/web-vue/dist/." "${INSTALL_DIR}/web_dist/"
}

run_python() {
  ensure_uv
  build_frontend
  ui_println "[$(text prefix_info)] $(text info_install_py)"
  (cd "${INSTALL_DIR}" && uv sync)

  ui_println "[$(text prefix_info)] $(text info_start_app) http://0.0.0.0:${PORT}"
  cd "${INSTALL_DIR}"
  export CHATGPT2API_AUTH_KEY="${AUTH_KEY}"
  export CHATGPT2API_THREAD_TOKENS="${THREAD_TOKENS}"
  export DATABASE_URL="${DATABASE_URL}"
  exec uv run uvicorn main:app --host 0.0.0.0 --port "${PORT}"
}

main() {
  parse_args "$@"
  choose_language

  if [[ -z "${MODE}" ]]; then
    MODE="$(prompt_mode_choice "docker")"
  else
    MODE="$(normalize_mode_choice "${MODE}")" || { echo "[$(text prefix_error)] $(text err_mode)" >&2; exit 1; }
  fi
  PORT="$(prompt_input "$(text prompt_port)" "${PORT}")"
  THREAD_TOKENS="$(prompt_input "$(text prompt_thread_tokens)" "${THREAD_TOKENS}")"
  INSTALL_DIR="$(prompt_input "$(text prompt_dir)" "${INSTALL_DIR}")"
  BRANCH="$(prompt_input "$(text prompt_branch)" "${BRANCH}")"
  DATABASE_URL="$(prompt_input "Application DATABASE_URL (blank = data/chatgpt2api.db)" "${DATABASE_URL}")"

  if [[ -z "${AUTH_KEY}" || "${AUTH_KEY}" == "your_secret_key_here" ]]; then
    AUTH_KEY="$(generate_auth_key)"
  fi
  AUTH_KEY="$(prompt_input "$(text prompt_auth)" "${AUTH_KEY}")"

  if [[ "${MODE}" == "docker" ]]; then
    if confirm "$(text prompt_warp)" "${WITH_WARP}"; then
      WITH_WARP="1"
    else
      WITH_WARP="0"
    fi
  fi

  validate_inputs
  if [[ "${MODE}" == "docker" ]]; then
    prepare_docker_bundle
  else
    prepare_repo
  fi
  write_default_config_json
  write_env_file

  if [[ "${MODE}" == "docker" ]]; then
    run_docker
  else
    run_python
  fi

  ui_println ""
  ui_println "[$(text prefix_done)] $(text done_ready): http://localhost:${PORT}"
  ui_println "[$(text prefix_done)] $(text done_auth): ${AUTH_KEY}"
}

main "$@"
