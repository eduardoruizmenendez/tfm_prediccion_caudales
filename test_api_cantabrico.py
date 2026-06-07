# test_nivel_besaya.py
import requests
from utils_adquisicion_datos import obtener_argumentos_y_config

if __name__ == "__main__":
    # 1. Cargamos el entorno global y extraemos tu API Key correcta
    _, _, credenciales = obtener_argumentos_y_config()
    api_key = str(credenciales.get("SAI_API_KEY", "")).strip()
    
    headers = {
        "X-API-KEY": api_key,
        "accept": "application/json"
    }
    
    # Apuntamos a la Estación 375 (Torrelavega) y a la Señal 1 (Nivel)
    url_test = "https://opendata.saichcantabrico.es/sai-pub-api/api/estacion/375/senal/1/serie"
    
    # Pedimos el mes completo de noviembre de 2024
    params = {
        "desde": "2024-11-01T00:00:00",
        "hasta": "2024-11-30T23:59:59"
    }
    
    print("=====================================================================")
    print("🧪 TEST DE DESCARGA REAL DE NIVEL - BESAYA")
    print("=====================================================================")
    print(f"📡 Solicitando datos de Nivel a: {url_test}")
    print(f"📅 Rango: {params['desde']} al {params['hasta']}")
    print("📡 Enviando petición...")
    
    try:
        res = requests.get(url_test, headers=headers, params=params, timeout=20)
        
        print(f"\n🔹 Código de Estado HTTP: {res.status_code}")
        
        if res.status_code == 200:
            datos = res.json()
            print("🏆 ¡CONEXIÓN EN VALOR DE HTTP 200 OK!")
            print(f"🔹 Tipo de datos devuelto por la CHC: {type(datos)}")
            
            print("\n🔍 CONTENIDO INTEGRAL DE LA RESPUESTA:")
            print("---------------------------------------------------------------------")
            # Si es un diccionario, imprimimos sus claves y una muestra
            if isinstance(datos, dict):
                print(f"🔑 Claves principales del JSON: {list(datos.keys())}")
                # Imprimimos los primeros 800 caracteres para no saturar la pantalla
                import json
                print(json.dumps(datos, indent=4)[:800])
            else:
                # Si es una lista o texto plano, lo volcamos directo
                print(str(datos)[:800])
            print("---------------------------------------------------------------------")
            
        else:
            print(f"\n❌ Error del servidor (HTTP {res.status_code})")
            print(f"Contenido del error: {res.text.strip()}")
            
    except Exception as e:
        print(f"\n❌ Error al procesar la respuesta: {e}")