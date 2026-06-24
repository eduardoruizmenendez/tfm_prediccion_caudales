import os
import xml.etree.ElementTree as ET

def save_config_to_xml(config_path: str, interval: int, test_mode: bool, max_caudal: float, altura_sensor_m: float, pin_pwm: int, aws_fetch_url: str, aws_push_url: str):
    """
    Serializa y persiste parámetros estructurales de calibración física e infraestructura en XML.

    Args:
        config_path (str): Ruta física del archivo XML de destino.
        interval (int): Frecuencia de muestreo del sensor ultrasónico en segundos.
        test_mode (bool): Flag de conmutación lógica a entorno virtualizado de pruebas.
        max_caudal (float): Cota superior de calibración para el cálculo hidráulico.
        altura_sensor_m (float): Distancia geométrica fija desde el transductor al lecho.
        pin_pwm (int): Asignación numérica del pin GPIO Broadcom (BCM).
        aws_fetch_url (str): Endpoint remoto de AWS para descarga meteorológica.
        aws_push_url (str): Endpoint remoto de AWS para transmisión agregada horaria.
    """
    root = ET.Element("config")
    settings = ET.SubElement(root, "settings")
    ET.SubElement(settings, "polling_interval_seconds").text = str(interval)
    ET.SubElement(settings, "test_mode").text = str(test_mode).lower()
    ET.SubElement(settings, "max_caudal_calibracion").text = str(max_caudal)
    ET.SubElement(settings, "altura_sensor_instalado_metros").text = str(altura_sensor_m)
    ET.SubElement(settings, "pin_pwm_gpio").text = str(pin_pwm)
    ET.SubElement(settings, "aws_fetch_url").text = str(aws_fetch_url)
    ET.SubElement(settings, "aws_push_url").text = str(aws_push_url)
    tree = ET.ElementTree(root)
    tree.write(config_path, encoding="utf-8", xml_declaration=True)

def load_config(config_path: str, sensor_name: str) -> dict:
    """
    Efectúa el análisis sintáctico del esquema XML o gestiona su autoregeneración por contingencia.

    Args:
        config_path (str): Ubicación física del archivo de entrada.
        sensor_name (str): Identificador unívoco del transductor de la estación.

    Returns:
        dict: Estructura normalizada de constantes operativas para el contexto de la aplicación.
    """
    default_fetch = "https://api.tu-servidor-aws.com/v1/fluvial/predict-data"
    default_push = "https://api.tu-servidor-aws.com/v1/fluvial/hourly-telemetry"
    try:
        if not os.path.exists(config_path):
            save_config_to_xml(config_path, 1, True, 10.0, 3.81, 23, default_fetch, default_push)
        tree = ET.parse(config_path)
        root = tree.getroot()
        
        def get_text(node_path, default):
            node = root.find(node_path)
            return node.text if node is not None else default

        return {
            "interval": int(get_text("settings/polling_interval_seconds", "1")),
            "test_mode": get_text("settings/test_mode", "true").lower() == "true",
            "max_caudal": float(get_text("settings/max_caudal_calibracion", "10.0")),
            "altura_sensor_m": float(get_text("settings/altura_sensor_instalado_metros", "3.81")),
            "pin_pwm": int(get_text("settings/pin_pwm_gpio", "23")),
            "aws_fetch_url": get_text("settings/aws_fetch_url", default_fetch),
            "aws_push_url": get_text("settings/aws_push_url", default_push),
            "urls": [sensor_name]
        }
    except Exception:
        # Fallback de aislamiento defensivo ante fallos críticos de I/O en almacenamiento secundario
        return {
            "interval": 1, "test_mode": True, "max_caudal": 10.0, "altura_sensor_m": 3.81,
            "pin_pwm": 23, "aws_fetch_url": default_fetch, "aws_push_url": default_push, "urls": [sensor_name]
        }