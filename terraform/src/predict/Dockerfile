# Imagen base de AWS Lambda con Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# Instalar dependencias del sistema (xgboost necesita libgomp)
RUN dnf install -y libgomp && dnf clean all

# Copiar requirements e instalar dentro de /var/task (LAMBDA_TASK_ROOT)
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copiar el handler
COPY handler.py ${LAMBDA_TASK_ROOT}/

# Comando que Lambda invoca
CMD [ "handler.lambda_handler" ]
