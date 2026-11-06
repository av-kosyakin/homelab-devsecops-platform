<!-- Замените OWNER/REPO на ваш github.com/<user>/<repo> перед первым push. -->

# Домашний стенд ИТ-инфраструктуры

![Secret scanning](https://github.com/OWNER/REPO/actions/workflows/security.yml/badge.svg)

Полигон для практики DevSecOps-дисциплин на реальном, работающем стенде: два «сервера»
на Docker, домен Active Directory, VPN-туннель между хостами, микросервисы во вложенном
Docker, инфраструктура как код и security-проверки в CI.

Каждое архитектурное решение задокументировано отдельным ADR с контекстом и
альтернативами, а не только финальным результатом — см. [docs/adr](docs/adr).

## Архитектура

```
┌──────────────────────────┐        WireGuard VPN        ┌──────────────────────────┐
│         server-a          │ ◄─────────────────────────► │         server-b          │
│   контроллер домена       │     Kerberos / LDAP auth     │   клиент домена (SSSD)    │
│   Samba AD + DNS           │                              │                           │
└──────────────────────────┘                               │  Docker-in-Docker:        │
                                                             │  Postgres → FastAPI       │
                                                             │    → Streamlit            │
                                                             │  Prometheus + Grafana     │
                                                             └──────────────────────────┘
```

Оба хоста управляются как код: Terraform описывает контейнеры и сети (`terraform/`),
Ansible — всё, что внутри: домен, VPN, микросервисы, доступ, 2FA (`ansible/`).

## Что внутри

- **Сеть и домен** — WireGuard-туннель между хостами, Samba AD как контроллер домена,
  SSSD на клиенте резолвит доменных пользователей через Kerberos/LDAP.
- **Микросервисы** — Postgres + FastAPI + Streamlit во вложенном Docker-движке на server-b.
- **Observability** — Prometheus снимает метрики с FastAPI, Grafana подключена
  автоматически через provisioning, готовый дашборд «API Overview».
- **2FA** — TOTP по SSH (PAM + google-authenticator) на клиенте домена. Сознательно
  **не** включено на самом контроллере домена — см. [ADR 0003](docs/adr/0003-no-domain-2fa-on-dc.md)
  (циклическая зависимость: нельзя входить в DC через сам DC).
- **Секреты** — Ansible Vault шифрует чувствительные переменные прямо в репозитории
  (`ansible/host_vars/server-b/vault.yml`); пароль от Vault никогда не коммитится.
  `.env` на хосте целиком генерируется Ansible-шаблоном (`env.j2`) из Vault-переменных,
  а не хранится файлом.

## Security-проверки в CI

Каждый push и pull request в `main` прогоняет четыре независимые проверки
(`.github/workflows/security.yml`):

| Проверка | Инструмент | Что ловит |
|---|---|---|
| Утечка секретов | [gitleaks](https://github.com/gitleaks/gitleaks) | Пароли, токены, ключи, случайно попавшие в коммит |
| Линт Ansible | [ansible-lint](https://github.com/ansible/ansible-lint) | Небезопасные и нерекомендуемые практики в ролях |
| IaC-сканирование (Terraform) | [Checkov](https://www.checkov.io/) | Небезопасные конфигурации инфраструктуры как код |
| Сканирование образов | [Trivy](https://aquasecurity.github.io/trivy/) | Известные уязвимости в собранных Docker-образах api/agent |

Часть джоб запущена в мягком режиме (`soft_fail` / `exit-code: 0`) — это сознательный
промежуточный шаг, пока находки не разобраны вручную, а не недоработка пайплайна.

Параллельно в проекте есть второй, приватный CI (`.gitlab-ci.yml`, self-hosted runner) —
dry-run проверки (`terraform plan`, `ansible --check`) перед реальным деплоем; подробности
в [ADR 0002](docs/adr/0002-gitlab-ci-self-hosted-runner.md).

## Как развернуть локально

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # укажите свой путь к данным контейнеров
terraform init
terraform apply

cd ../ansible
ansible-vault create host_vars/server-b/vault.yml   # свои секреты вместо примера
ansible-playbook -i inventory.ini site.yml --vault-password-file .vault_pass
```

## Структура репозитория

```
ansible/      — роли и плейбуки (домен, VPN, микросервисы, доступ, 2FA)
terraform/    — описание контейнеров и сетей
microservices/— код API, агента, конфиги Prometheus/Grafana
docs/adr/     — архитектурные решения с обоснованием
CHANGELOG.md  — история изменений по датам
```

## Известные ограничения

- Terraform state хранится локально, а не в удалённом backend — для одной машины
  осознанный компромисс, см. [ADR 0001](docs/adr/0001-terraform-for-docker-infra.md).
- `.gitlab-ci.yml` в этом репозитории — витрина реального приватного пайплайна;
  запускать его как есть не получится без self-hosted runner'а и своих CI-переменных.
- Checkov почти не даёт находок для провайдера `kreuzwerker/docker` — большинство
  встроенных политик рассчитаны на AWS/Azure/GCP/Kubernetes, это ожидаемо.
