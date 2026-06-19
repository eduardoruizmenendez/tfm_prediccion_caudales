# Imagen base oficial de AWS Lambda con Python 3.11
FROM public.ecr.aws/lambda/python:3.11

# Copiar requirements e instalar solo con wheels binarios (la imagen
# base no incluye compilador C). Las wheels manylinux ya empaquetan
# libgomp y demás libs nativas que xgboost necesita.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir --only-binary=:all: -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copiar el handler
COPY handler.py ${LAMBDA_TASK_ROOT}/

# Comando que Lambda invoca
CMD [ "handler.lambda_handler" ]
