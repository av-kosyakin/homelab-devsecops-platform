# 0002. GitLab CI/CD с self-hosted shell-executor Runner для линтинга и dry-run проверок

## Статус
Принято — 2026-09-13

## Контекст
После ADR 0001 (переход на Terraform) появилась цель — автоматически проверять и Terraform, и Ansible при каждом push в `main`, вместо ручного запуска `terraform plan` / `ansible --check --diff`.

Ограничения, определившие решение:
- И Terraform (провайдер `kreuzwerker/docker`), и Ansible (подключение `community.docker.docker` в `inventory.ini`) работают напрямую с локальным Docker/OrbStack на конкретном Mac — по сети до него не достучаться. Облачный, эфемерный раннер GitLab (shared/instance runners) не может ни увидеть этот Docker, ни воспроизвести `ansible_connection=community.docker.docker`.
- Файл состояния Terraform (`terraform.tfstate`) не хранится в git (правильная практика) — в чистом checkout CI его нет, поэтому "из коробки" `terraform plan` показал бы создание всей инфраструктуры с нуля вместо реального дрейфа.
- GitLab.com требует верификацию личности (по телефону) перед запуском любого пайплайна, если для проекта включены "instance runners" (бывшие "shared runners") — даже если реально пайплайн на них никогда не попадёт. У владельца аккаунта не было номера, подходящего для этой верификации.

## Решение
- Установить `gitlab-runner` на Mac через Homebrew, зарегистрировать как **project runner**, executor — **shell** (не docker) с тегом `macbook-air`. Shell executor даёт джобе то же окружение (Docker-сокет, `terraform`, `ansible-playbook`, уже настроенные SSH/Docker), что и ручные запуски на этой машине.
- Явно задать `environment = ["PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/sbin:/usr/sbin"]` в конфиге раннера — `terraform`/`ansible-playbook` лежат в `/opt/homebrew/bin`, а `docker` резолвится из `/usr/local/bin`; голый запуск через launchd не наследует PATH интерактивного шелла.
- **Отключить "instance runners" для проекта** (Settings → CI/CD → Runners → вкладка Instance) — именно это позволило запускать пайплайны без верификации по телефону, раз используется только свой раннер. Подтверждено на форуме GitLab: "A user can also run pipelines without providing a credit or debit card if they use their own runner and disable shared runners for their project."
- Пайплайн (`.gitlab-ci.yml`) запускается на каждый push в `main` (`workflow: rules: if $CI_COMMIT_BRANCH == "main"`), два этапа:
  - `lint`: `terraform fmt -check` / `validate`, `ansible-playbook --syntax-check`.
  - `plan`: `terraform plan` (state подкладывается из реальной рабочей копии по абсолютному пути — иначе CI его не видит) и `ansible-playbook --check --diff` против живых контейнеров.
- Из CI никогда не выполняется `apply`/реальные изменения — соответствует уже принятой практике "сначала dry-run" для ручной работы с Terraform/Ansible.
- Пароль от Ansible Vault хранится как masked+protected CI/CD-переменная (`ANSIBLE_VAULT_PASSWORD`), пишется во временный файл только на время джобы и удаляется в `after_script`.

## Последствия

Положительные:
- Каждый push в `main` теперь автоматически перепроверяет и Terraform, и Ansible против реально работающего стенда, без ручных команд.
- Не используется ни секунды облачных вычислений GitLab — всё работает на уже имеющемся железе, и антифрод-верификация GitLab больше не блокирует пайплайны (после отключения instance runners).

Известные ограничения:
- Подстановка `terraform.tfstate` из захардкоженного абсолютного пути (`/Users/<user>/it-infra-platform/terraform/terraform.tfstate`) привязывает пайплайн к этой конкретной машине — приемлемо для домашней лабы на одном компьютере, но потребует настоящего remote backend (например, GitLab-managed Terraform state), если появится второй раннер/машина.
- С отключёнными instance runners CI-задачи могут выполняться только на этом конкретном Mac — если он выключен/спит, пайплайны встают в очередь до его возвращения.
- Shell executor выполняет скрипты пайплайна с правами обычного пользователя системы — приемлемо для учебного проекта с одним мейнтейнером, но не паттерн для повторного использования в команде без дополнительной изоляции (например, docker executor или отдельный непривилегированный CI-пользователь).

## Рассмотренные альтернативы
- Облачные shared/instance runners GitLab — отклонено: не видят локальный Docker и `community.docker.docker`, плюс требуют верификацию личности, которую не пройти без телефона.
- Docker executor для собственного раннера — отклонено пока: потребовал бы Docker-in-Docker или монтирования Docker-сокета хоста в контейнеры джоб, что добавляет сложность без реальной пользы на единственной всегда-локальной машине; shell executor и так имеет прямой доступ.
