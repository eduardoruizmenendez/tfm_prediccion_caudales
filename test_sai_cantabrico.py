# test_chc_catalogos.py
import requests
from utils_adquisicion_datos import obtener_argumentos_y_config

if __name__ == "__main__":
    # Forzamos la carga de la configuración del besaya para extraer sus credenciales
    # Pasamos los argumentos simulados para que no falle el parser CLI si lo ejecutas plano
    id_cuenca, parametros, credenciales = obtener_argumentos_y_config()
    
    print("=====================================================================")
    print("📡 SCRIPT DE EXPLORACIÓN DE CATÁLOGOS - SAIH CANTÁBRICO")
    print("=====================================================================\n")
    
    api_key = credenciales.get("SAI_API_KEY")
    if not api_key:
        print("❌ Error: No se ha detectado 'sai_api_key' en tus credenciales.")
        exit()
        
    headers = {
        "X-API-KEY": api_key,
        "accept": "application/json"
    }
    
    # -------------------------------------------------------------------------
    # FASE 1: EXPLORACIÓN DE ESTACIONES
    # -------------------------------------------------------------------------
    url_estaciones = "https://opendata.saichcantabrico.es/sai-pub-api/api/estaciones"
    print(f"📡 Solicitando catálogo completo de estaciones a: {url_estaciones}")
    
    try:
        res_est = requests.get(url_estaciones, headers=headers, timeout=20)
        if res_est.status_code == 200:
            estaciones = res_est.json()
            print(f"✅ ¡Éxito! Se han encontrado {len(estaciones)} estaciones en el sistema.\n")
            
            print("🔍 Buscando coincidencias para el Besaya / Torrelavega...")
            encontradas = 0
            for est in estaciones:
                # Convertimos todo a texto para buscar de forma flexible
                est_str = str(est).lower()
                if "torrelavega" in est_str or "besaya" in est_str or "a085" in est_str:
                    encontradas += 1
                    print(f"\n📌 Coincidencia #{encontradas} detectada:")
                    # Imprimimos el objeto completo de la estación para ver sus claves
                    for k, v in est.items():
                        print(f"   -> {k}: {v}")
            
            if encontradas == 0:
                print("⚠️  No se encontró ninguna estación con esos nombres en el catálogo.")
                print("💡 Imprimiendo las primeras 5 estaciones para comprobar la estructura:")
                for est in estaciones[:5]:
                    print(f"   -> {est}")
        else:
            print(f"❌ Error al consultar estaciones. Código HTTP: {res_est.status_code}")
            
    except Exception as e:
        print(f"❌ Fallo de conexión en la fase de estaciones: {e}")

    print("\n" + "-"*70 + "\n")

    # -------------------------------------------------------------------------
    # FASE 2: EXPLORACIÓN DE SEÑALES GENERALES
    # -------------------------------------------------------------------------
    url_senales = "https://opendata.saichcantabrico.es/sai-pub-api/api/senales"
    print(f"📡 Solicitando catálogo maestro de señales a: {url_senales}")
    
    try:
        res_sen = requests.get(url_senales, headers=headers, timeout=20)
        if res_sen.status_code == 200:
            senales = res_sen.json()
            print(f"✅ ¡Éxito! Se han encontrado {len(senales)} tipos de señales maestros.\n")
            
            print("🔍 Buscando señales de tipo Caudal o Nivel...")
            for sen in senales:
                sen_str = str(sen).lower()
                if "caudal" in sen_str or "nivel" in sen_str or "flujo" in sen_str:
                    print(f"📌 Señal detectada:")
                    for k, v in sen.items():
                        print(f"   -> {k}: {v}")
                    print()
        else:
            print(f"❌ Error al consultar señales. Código HTTP: {res_sen.status_code}")
            
    except Exception as e:
        print(f"❌ Fallo de conexión en la fase de señales: {e}")

    print("=====================================================================")
    print("🏁 FIN DEL SCRIPT DE PRUEBA")
    print("=====================================================================")