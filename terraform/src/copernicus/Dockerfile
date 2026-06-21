FROM public.ecr.aws/lambda/python:3.11

# cdsapi + xarray + netcdf4 superan 250MB → container obligatorio
RUN pip install --no-cache-dir \
    cdsapi==0.7.5 \
    xarray==2024.10.0 \
    netcdf4==1.7.2 \
    pandas==2.2.2 \
    numpy==2.1.1 \
    boto3==1.35.0

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
