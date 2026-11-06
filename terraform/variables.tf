variable "lab_data_root" {
  description = "Абсолютный путь на хосте, где лежат writable-данные контейнеров (/root внутри server-a и server-b монтируется сюда). Задайте в terraform.tfvars."
  type        = string
}
