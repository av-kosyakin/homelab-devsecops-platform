# Changelog

Все заметные изменения проекта фиксируются в этом файле.
Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/).

## [Unreleased]

## 2026-09-28 — Observability: Prometheus + Grafana поверх FastAPI-метрик
### Added
- В API подключён prometheus-fastapi-instrumentator: реальный эндпоинт /metrics (задержка запросов, счётчик по эндпоинтам), без изменения бизнес-логики main.py.
- В docker-compose.yml добавлены сервисы prometheus (скрейпит api:8000/metrics каждые 15с) и grafana (источник данных Prometheus подключается автоматически через provisioning, без ручной настройки в UI).
- Роль microservices дополнена копированием конфигов prometheus/prometheus.yml и grafana/provisioning/.
- Пароль администратора Grafana вынесен в Ansible Vault (vault_grafana_admin_password), как и остальные секреты стенда.
- Собран первый дашборд «API Overview»: request rate по эндпоинтам и средняя задержка запросов.

### Fixed
- docker-compose v1.29.2 (ставится вместе с пакетом docker.io по умолчанию) несовместим с современным Docker Engine — при пересоздании контейнера падает с KeyError: 'ContainerConfig'. Установлен актуальный плагин docker-compose-v2.
- Доступ к Grafana/Prometheus с Mac организован через SSH-туннель (-L 3000:localhost:3000 -L 9090:localhost:9090) поверх уже проброшенного порта SSH, а не через новые port mapping в Terraform — чтобы не пересоздавать контейнер server-b и не терять состояние членства в домене (machine-account keytab, которое не управляется Ansible).

## 2026-09-21 — SSH-доступ доменных пользователей: три независимые причины отказа
### Added
- Роль base_access (общая для всех хостов): включает и держит sshd включённым, снимает зависший /run/nologin, добавляет pam_mkhomedir для автосоздания домашних папок доменных пользователей.
- В sssd.conf.j2 — явный ad_server = dc.internal.local, чтобы не зависеть от автообнаружения через DNS SRV-записи.
- В роли sssd — задача, приводящая /etc/resolv.conf на server-b к DNS AD-контроллера (10.10.100.1), нужная для собственного механизма поиска серверов SSSD (отдельного от krb5.conf, которым пользуется kinit).

### Fixed
- SSH-логин доменным пользователем (administrator) не проходил по трём независимым причинам одновременно: (1) sshd не был включён — enable-symlink стирается стартовой командой контейнера при каждом рестарте; (2) server-b не мог резолвить server-a через DNS для служебного обнаружения SSSD (раньше это не требовалось — kinit использует статический krb5.conf); (3) /run/nologin навсегда завис, потому что зависимость, которая должна была подтянуть systemd-user-sessions.service, была срезана вместе с остальными *.wants/* при старте контейнера.


## 2026-09-21 — TOTP-двухфакторная аутентификация по SSH на server-b (ADR 0003)
### Added
- Роль mfa (Ansible): PAM + libpam-google-authenticator для SSH на группе domain_clients (сейчас — только server-b); sshd_config переведён на KbdInteractiveAuthentication yes / PasswordAuthentication no, чтобы PAM мог провести отдельный диалог для TOTP-кода после проверки доменного пароля через SSSD.
- ADR 0003: решение не подключать доменных пользователей и 2FA к server-a (контроллеру домена) — во избежание циклической зависимости «нужен AD, чтобы зайти на сервер, который поднимает AD», и из-за отсутствия winbind/idmap для резолва доменных учёток в POSIX-аккаунты на самом DC.

### Changed
- server-a: администрирование по-прежнему через docker exec, без SSH-доступа доменных пользователей и без 2FA; все экспериментальные изменения (PAM, sshd_config, пакет libpam-google-authenticator) полностью откачены.

## 2026-09-13 — GitLab CI: линтинг + dry-run на каждый push в main
### Added
- Собственный GitLab Runner (shell executor) на Mac, тег `macbook-air`; общие (instance) раннеры для проекта отключены.
- `.gitlab-ci.yml`: стадия `lint` (`terraform fmt/validate`, `ansible-playbook --syntax-check`) и стадия `plan` (`terraform plan`, `ansible-playbook --check --diff`) на каждый push в `main`.
- Секрет `ANSIBLE_VAULT_PASSWORD` — маскированная и protected CI/CD-переменная.

### Fixed
- Отключение instance runners для проекта позволило обойти требование верификации аккаунта по телефону GitLab (не было доступного номера) без ущерба для безопасности — раннер и так свой, физически на этой же машине.

## 2026-09-07 — Terraform для управления Docker-инфраструктурой
### Added
- Каталог `terraform/` с описанием сетей (`net_a`, `net_b`) и контейнеров (`server-a`, `server-b`) через провайдер `kreuzwerker/docker`.
- Оба существующих контейнера и обе сети взяты под управление Terraform через `terraform import`, без пересоздания — весь наработанный стейт (Samba AD, WireGuard, вложенный Docker) сохранён.

### Changed
- `~/it-infra-lab/docker-compose.yml` больше не источник правды для топологии — им стал `terraform/main.tf`.

## 2026-09-02 — Роли docker_engine и microservices, секреты в Vault
### Added
- Ansible-роль `docker_engine`: установка пакета, `storage-driver=vfs`, автозапуск вложенного Docker.
- Ansible-роль `microservices`: деплой api/agent из репозитория; секреты вынесены в `host_vars/server-b/vault.yml` и зашифрованы Ansible Vault.

### Fixed
- Ansible-роли `samba_ad` и `sssd`: восстановление домена после перезапуска контейнера (unmask+enable нужных systemd-юнитов); `sssd.conf` собирается из шаблона с `ldap_sasl_authid`, вычисляемым через `inventory_hostname`.

## 2026-09-01 — Микросервисы и JWT
### Added
- Код микросервисов (FastAPI + Postgres + Streamlit) добавлен в репозиторий.
- JWT-аутентификация в API (`/login` выдаёт токен, остальные эндпоинты требуют валидный токен).

### Changed
- Секреты микросервисов вынесены в `.env`.

## 2026-08-31 — Ansible-роль wireguard
### Added
- Установка пакетов WireGuard через Ansible.
- Генерация и переиспользование ключей, шаблон `wg0.conf`, автозапуск туннеля.

## 2026-08-27 — 2026-08-28 — Начало проекта
### Added
- Первая структура репозитория: README, `.gitignore`, инвентарь Ansible.
