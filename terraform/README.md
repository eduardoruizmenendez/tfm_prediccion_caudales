# Infraestructura cloud (Terraform · V1)

Despliegue del *pipeline* hidrológico en AWS, región `eu-south-2` (Madrid).
Alcance V1: cuenca del **Urumea** únicamente.

## Recursos provisionados

| Tipo | Nombre | Propósito |
|---|---|---|
| S3 bucket | `tfm-caudales-{accountId}` | Data Lake (`bronze/ silver/ gold/ models/`) |
| SSM Parameter Store | 3 entradas en `/tfm/...` | Credenciales API (AEMET, Euskalmet) |
| IAM Role | `tfm-caudales-lambda-exec` | Identidad común de las Lambdas |
| IAM Role | `tfm-caudales-scheduler-invoke` | Identidad de EventBridge |
| ECR repository | `tfm-caudales-predict` | Imagen Docker de la Lambda de inferencia |
| Lambda (zip) | `tfm-caudales-openmeteo` | Ingesta horaria pronóstico Open-Meteo |
| Lambda (zip) | `tfm-caudales-aemet-actual` | Ingesta horaria AEMET (estación 1024E) |
| Lambda (zip) | `tfm-caudales-hidro-actual` | Ingesta horaria Euskalmet (C0F0 Ereñozu) |
| Lambda (zip) | `tfm-caudales-dataset` | Feature engineering diario → `gold/` |
| Lambda (container) | `tfm-caudales-predict` | Inferencia ensemble BiLSTM + XGBoost |
| Lambda Function URL | endpoint público | Endpoint de inferencia (sin API Gateway) |
| EventBridge Scheduler ×4 | crons horario y diario | Disparadores temporales |

## Despliegue paso a paso

### 1 · Empaquetar dependencias de las Lambdas zip

```bash
./build.sh
```

Esto baja wheels Linux x86_64 a cada `src/<lambda>/` para que las
extensiones C (cryptography para Euskalmet) funcionen en el runtime
Lambda.

### 2 · `terraform init` y plan inicial

```bash
terraform init
terraform plan
```

### 3 · Construir y subir la imagen de la Lambda de inferencia

Antes del primer `terraform apply` que cree la Lambda contenedor,
hay que subir al menos una imagen a ECR para que el `aws_ecr_image`
data source no falle.

```bash
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=eu-south-2
REPO="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/tfm-caudales-predict"

# Primera vez: crear el repositorio antes de tener la Lambda
terraform apply -target=aws_ecr_repository.predict

# Login al registro
aws ecr get-login-password --region $REGION | \
    docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"

# Build y push
cd src/predict
docker build -t tfm-caudales-predict:latest .
docker tag tfm-caudales-predict:latest "$REPO:latest"
docker push "$REPO:latest"
cd ../..
```

### 4 · Apply completo

```bash
terraform apply
```

### 5 · Rellenar credenciales en SSM

Tras el primer apply, los tres parámetros tienen valor placeholder
`REPLACE_ME`. Sobreescribir con los valores reales (sin que Terraform
los pise gracias a `lifecycle.ignore_changes`):

```bash
# Clave API de AEMET (la que recibes en el portal de desarrolladores)
aws ssm put-parameter \
    --name "/tfm/aemet/api-key" \
    --value "TU_CLAVE_AEMET" \
    --type SecureString --overwrite

# Clave privada PEM de Euskalmet (multilínea desde fichero)
aws ssm put-parameter \
    --name "/tfm/euskalmet/private-key" \
    --value "file://./euskalmet_private.pem" \
    --type SecureString --overwrite

# Email registrado en Open Data Euskadi
aws ssm put-parameter \
    --name "/tfm/euskalmet/email" \
    --value "tu-email@dominio.tld" \
    --type String --overwrite
```

### 6 · Verificación

Disparar manualmente una Lambda para validar:

```bash
aws lambda invoke --function-name tfm-caudales-openmeteo /tmp/out.json
cat /tmp/out.json
```

Una hora después, verificar que llegan datos al bucket:

```bash
aws s3 ls "s3://$(terraform output -raw data_lake_bucket)/bronze/openmeteo/urumea/" --recursive
```

## Flujo de datos

```
EventBridge cron(5 * * * ? *) ────► lambda openmeteo     ──►  bronze/openmeteo/...
EventBridge cron(5 * * * ? *) ────► lambda aemet_actual  ──►  bronze/aemet_actual/...
EventBridge cron(5 * * * ? *) ────► lambda hidro_actual  ──►  bronze/hidro/...
                                                                       │
                                                                       ▼
EventBridge cron(0 4 * * ? *) ────► lambda dataset ────────────────►  gold/urumea/matriz_features.parquet

SageMaker Studio Lab (Daniel) ──── lee gold/, entrena, sube ────►  models/urumea/current/...
                                                                       │
HTTPS GET/POST a Function URL ────► lambda predict (container)  ◄──────┘
                                                                       │
                                                                       ▼
                                                              JSON con 5 horizontes
```

## Pendiente para V2

- Cuenca del **Besaya** (SAIH Cantábrico, sin JWT, requiere
  `X-API-KEY` en cabecera).
- Ingesta **histórica** de Copernicus (ERA5-Land y GloFAS): se
  necesita layer custom con `xarray` + `netCDF4` o ejecutar one-shot
  desde CloudShell con `cdsapi`.
- Ingesta **histórica** de AEMET y series largas de Euskalmet.
- Mecanismo de **alerta** ante predicción de riesgo alto.
- Comunicación con el **dispositivo intermedio** (Eduardo): MQTT
  vía IoT Core o HTTPS hacia la Function URL de predict.
- Versionado del modelo (`models/v1/`, `models/v2/`, alias
  `current` apuntando a la versión activa).

## Coste estimado

≈ 0,20 USD/mes en estado estacionario, asumiendo *no* Free Tier:
- S3 a precio estándar de eu-south-2 con ~1 GiB de datos.
- ECR con ~600 MB de imagen (despreciable).
- Lambda, EventBridge, Parameter Store, CloudWatch Logs: *Always Free*
  cubre con holgura.

Con Free Tier vigente: ≈ 0 USD/mes.
