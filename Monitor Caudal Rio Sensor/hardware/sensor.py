import asyncio
import time
import random
import numpy as np
import lgpio

def _medir_pulso_high_precision(lgpio_handle, pin_pwm, timeout_sec: float = 0.06) -> float:
    """
    Ejecuta un muestreo síncrono de alta velocidad por captura de flancos lógicos sobre el GPIO.
    Se ejecuta en un hilo aislado dedicado para evadir las latencias internas del kernel.

    Args:
        lgpio_handle (int): Descriptor de contexto activo del chip lgpio.
        pin_pwm (int): Mapeo físico numérico BCM del pin bajo análisis.
        timeout_sec (float): Ventana de desbordamiento de seguridad (guard timeout).

    Returns:
        float: Duración de la fase activa del pulso en segundos, o -1.0 si expira el tiempo.
    """
    start_timeout = time.perf_counter()
    
    # Estabilización de la línea lógicas ante rebotes capacitivos residuales
    while lgpio.gpio_read(lgpio_handle, pin_pwm) == 1:
        if time.perf_counter() - start_timeout > timeout_sec: return -1.0
        
    # Interceptación del flanco de subida (Start Echo Pulse)
    while lgpio.gpio_read(lgpio_handle, pin_pwm) == 0:
        if time.perf_counter() - start_timeout > timeout_sec: return -1.0
    t_subida = time.perf_counter()
    
    # Interceptación del flanco de bajada (End Echo Pulse)
    while lgpio.gpio_read(lgpio_handle, pin_pwm) == 1:
        if time.perf_counter() - start_timeout > timeout_sec: return -1.0
    t_bajada = time.perf_counter()
    
    return t_bajada - t_subida

async def read_sensor_pwm(app) -> tuple:
    """
    Abstrae el subsistema de hardware e instrumenta la adquisición telemétrica multivariable.

    Args:
        app: Instancia de la aplicación contenedora global (RiverMonitorAI).

    Returns:
        tuple: Vectores físicos calculados en formato (caudal, distancia_m, altura_agua_m).
    """
    async with app.config_lock:
        max_caudal = app.config["max_caudal"]
        test_mode = app.config["test_mode"]
        altura_sensor_m = app.config["altura_sensor_m"]
        pin_pwm = app.config["pin_pwm"]

    if test_mode or app.lgpio_handle is None:
        hist = app.historico_por_estacion[app.sensor_name]
        ultimo_caudal = hist[-1]["value"] if hist else (max_caudal * 0.25)
        factor_riesgo_red = 1.25 if app.modo_cloud_caido else 1.0
        if app.cloud_lluvia_prevista_6h > 40.0 or app.modo_cloud_caido:
            caudal_sim = round(min(ultimo_caudal + random.uniform(0.05, max_caudal * 0.04 * factor_riesgo_red), max_caudal), 2)
        else:
            caudal_sim = round(min(max(ultimo_caudal + random.uniform(-max_caudal * 0.02, max_caudal * 0.025), 0.3), max_caudal), 2)
        dist_sim_m = max(altura_sensor_m - (caudal_sim * (altura_sensor_m / max_caudal)), 0.15)
        return caudal_sim, round(dist_sim_m, 3), round(max(altura_sensor_m - dist_sim_m, 0.0), 3)

    try:
        muestras_distancia = []
        for _ in range(5):
            # Delegación de la rutina síncrona sutil al pool de hilos para no congelar el Event Loop
            duracion_segundos = await asyncio.to_thread(_medir_pulso_high_precision, app.lgpio_handle, pin_pwm)
            if duracion_segundos < 0: continue
            
            # Algoritmo de escala física del sensor de ultrasonidos MaxBotix MB1010
            distancia_pulgadas = (duracion_segundos * 1_000_000.0) / 147.0
            distancia_metros = distancia_pulgadas * 0.0254
            if 0.15 <= distancia_metros <= 7.65: muestras_distancia.append(distancia_metros)
            
        if len(muestras_distancia) < 3: return None, None, None
        
        # Filtrado por mediana móvil para neutralizar ruido analógico transitorio
        distancia_filtrada = float(np.median(muestras_distancia))
        hist = app.historico_por_estacion[app.sensor_name]
        
        # Suavizado exponencial amortiguado para estabilización hidrométrica continua
        if hist: distancia_filtrada = (distancia_filtrada * 0.85) + (hist[-1]["distancia_m"] * 0.15)
        
        altura_agua_metros = max(altura_sensor_m - distancia_filtrada, 0.0)
        caudal_calculado = max_caudal - ((distancia_filtrada / 0.0254) * (max_caudal * 0.008))
        return round(min(max(caudal_calculado, 0.3), max_caudal), 2), round(distancia_filtrada, 3), round(altura_agua_metros, 3)
    except Exception as e:
        app._registrar_accion(f"ERROR SUBSISTEMA HARDWARE: {e}")
        return None, None, None