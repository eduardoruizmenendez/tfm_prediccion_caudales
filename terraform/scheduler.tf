# EventBridge Scheduler — disparadores temporales de las Lambdas
#
# Estrategia V1: ingesta horaria sincronizada al minuto 5 (deja margen
# a que las APIs publiquen los datos de la hora pasada), dataset una
# vez al día por la madrugada.
#
# Cuota gratuita: 14 millones de invocaciones / mes (Always Free).
# Usaremos del orden de 96 (3 schedulers × 24 h × 30 días + dataset
# diario × 30 = ~2.200/mes). Holgura del 99,98 %.

# Rol que asume EventBridge para invocar las Lambdas
resource "aws_iam_role" "scheduler_invoke" {
  name = "${local.project}-scheduler-invoke"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke_lambdas" {
  name = "invoke-tfm-lambdas"
  role = aws_iam_role.scheduler_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "lambda:InvokeFunction"
      Resource = [
        aws_lambda_function.openmeteo.arn,
        aws_lambda_function.aemet_actual.arn,
        aws_lambda_function.hidro_actual.arn,
        aws_lambda_function.dataset.arn,
      ]
    }]
  })
}

# ---------------------------------------------------------------------
# Schedulers horarios (minuto 5)
# ---------------------------------------------------------------------
resource "aws_scheduler_schedule" "openmeteo_hourly" {
  name        = "${local.project}-openmeteo-hourly"
  description = "Ingesta horaria de pronóstico Open-Meteo (Urumea)"
  state       = "DISABLED" # V1: pipeline limitado a AEMET. Reactivar quitando esta línea.

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.openmeteo.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

resource "aws_scheduler_schedule" "aemet_actual_hourly" {
  name        = "${local.project}-aemet-actual-hourly"
  description = "Ingesta horaria de observaciones AEMET (estación 1024E)"

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.aemet_actual.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

resource "aws_scheduler_schedule" "hidro_actual_hourly" {
  name        = "${local.project}-hidro-actual-hourly"
  description = "Ingesta horaria de telemetría Euskalmet (C0F0 Ereñozu)"
  state       = "DISABLED" # V1: pipeline limitado a AEMET. Reactivar quitando esta línea.

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.hidro_actual.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}

# ---------------------------------------------------------------------
# Scheduler diario para la generación de la matriz de features (04:00 UTC)
# ---------------------------------------------------------------------
resource "aws_scheduler_schedule" "dataset_daily" {
  name        = "${local.project}-dataset-daily"
  description = "Generación diaria de la matriz de características desde bronze hacia gold"

  flexible_time_window { mode = "OFF" }

  schedule_expression          = "cron(0 4 * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.dataset.arn
    role_arn = aws_iam_role.scheduler_invoke.arn
  }
}
