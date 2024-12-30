import time
import json
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# Cargar configuración desde JSON
def cargar_config():
    """Carga la configuración desde el archivo JSON"""
    ruta_config = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(ruta_config, 'r') as f:
        return json.load(f)

# Cargar configuración
config = cargar_config()

# Configuración inicial desde JSON
SYMBOL = config['trading']['symbol']
INTERVAL = config['trading']['interval']
LOOKBACK_PERIOD = config['trading']['lookback_period']
BASE_URL = "https://api.binance.com/api/v3"

class VRVP:
    def __init__(self, num_niveles=24, va_porcentaje=70):
        self.num_niveles = num_niveles
        self.va_porcentaje = va_porcentaje
    
    def calcular_vrvp(self, df):
        """Calcula el Perfil de Volumen de Rango Visible"""
        # Encontrar el rango de precios
        precio_max = df['high'].max()
        precio_min = df['low'].min()
        
        # Crear niveles de precio
        niveles = np.linspace(precio_min, precio_max, self.num_niveles)
        volumen_por_nivel = np.zeros(self.num_niveles - 1)
        
        # Calcular volumen por nivel
        for i in range(len(df)):
            for j in range(len(niveles) - 1):
                if (df['low'].iloc[i] <= niveles[j+1] and 
                    df['high'].iloc[i] >= niveles[j]):
                    volumen_por_nivel[j] += df['volume'].iloc[i]
        
        # Encontrar el Point of Control (POC)
        poc_index = np.argmax(volumen_por_nivel)
        poc_precio = (niveles[poc_index] + niveles[poc_index + 1]) / 2
        
        # Calcular Value Area (70% del volumen total)
        total_volumen = np.sum(volumen_por_nivel)
        volumen_objetivo = total_volumen * (self.va_porcentaje / 100)
        
        # Expandir desde el POC hasta alcanzar el volumen objetivo
        volumen_acumulado = volumen_por_nivel[poc_index]
        superior_idx = poc_index
        inferior_idx = poc_index
        
        while volumen_acumulado < volumen_objetivo and (superior_idx < len(volumen_por_nivel)-1 or inferior_idx > 0):
            vol_superior = volumen_por_nivel[superior_idx + 1] if superior_idx < len(volumen_por_nivel)-1 else 0
            vol_inferior = volumen_por_nivel[inferior_idx - 1] if inferior_idx > 0 else 0
            
            if vol_superior > vol_inferior and superior_idx < len(volumen_por_nivel)-1:
                superior_idx += 1
                volumen_acumulado += vol_superior
            elif inferior_idx > 0:
                inferior_idx -= 1
                volumen_acumulado += vol_inferior
        
        va_superior = niveles[superior_idx + 1]
        va_inferior = niveles[inferior_idx]
        
        return {
            'niveles': niveles,
            'volumen_por_nivel': volumen_por_nivel,
            'poc_precio': poc_precio,
            'va_superior': va_superior,
            'va_inferior': va_inferior,
            'volumen_total': total_volumen,
            'volumen_va': volumen_acumulado
        }
    
    def analizar_señales(self, vrvp_data, precio_actual):
        """Analiza señales basadas en el VRVP - Solo señales fuera de las Value Areas"""
        poc_precio = vrvp_data['poc_precio']
        va_superior = vrvp_data['va_superior']
        va_inferior = vrvp_data['va_inferior']
        
        # Solo generar señales cuando el precio está fuera de las Value Areas
        if precio_actual > va_superior:
            return "VENTA", "Precio por encima del Value Area Superior"
        elif precio_actual < va_inferior:
            return "COMPRA", "Precio por debajo del Value Area Inferior"
        else:
            return "NEUTRAL", "Precio dentro de las Value Areas"

def obtener_precio_actual():
    """Obtiene el precio actual del par de trading"""
    endpoint = f"{BASE_URL}/ticker/price"
    params = {'symbol': SYMBOL}
    
    response = requests.get(endpoint, params=params)
    if response.status_code != 200:
        raise Exception("Error al obtener el precio actual")
    
    return float(response.json()['price'])

def guardar_en_csv(tipo_orden, precio_actual, va_superior, va_inferior):
    """Guarda la información de la orden en un archivo CSV"""
    # Crear un DataFrame con la información
    data = {
        'Fecha y Hora': [datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
        'Precio': [precio_actual],
        'Valor Area Superior': [va_superior],
        'Valor Area Inferior': [va_inferior],
        'Tipo de Orden': [tipo_orden]
    }
    
    df = pd.DataFrame(data)
    
    # Nombre del archivo CSV
    archivo_csv = 'ordenes.csv'
    
    # Agregar los datos sin sobrescribir
    df.to_csv(archivo_csv, mode='a', header=False, index=False)

def crear_csv():
    """Crea el archivo CSV si no existe"""
    archivo_csv = 'ordenes.csv'
    if not os.path.exists(archivo_csv):
        # Crear un DataFrame vacío y guardar el archivo con la cabecera
        df = pd.DataFrame(columns=['Fecha y Hora', 'Precio', 'Valor Area Superior', 'Valor Area Inferior', 'Tipo de Orden'])
        df.to_csv(archivo_csv, mode='w', header=True, index=False)

def mostrar_datos_tiempo_real():
    """Muestra datos y análisis VRVP en tiempo real"""
    vrvp = VRVP()
    
    # Crear el archivo CSV al iniciar el programa
    crear_csv()
    
    # Obtener el intervalo de actualización directamente del JSON
    intervalo_actualizacion = config['actualizacion']['intervalo_segundos']
    
    print("El programa se actualizará automáticamente según el intervalo configurado.")
    
    while True:
        try:
            df = obtener_datos_binance()
            vrvp_data = vrvp.calcular_vrvp(df)
            precio_actual = obtener_precio_actual()
            señal, razón = vrvp.analizar_señales(vrvp_data, precio_actual)
            
            # Calcular la distancia a las áreas
            distancia_superior, distancia_inferior = calcular_distancia_areas(precio_actual, vrvp_data['va_superior'], vrvp_data['va_inferior'])
            
            print("\n" + "="*50)
            print(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Símbolo: {SYMBOL}")
            print(f"Temporalidad: {config['trading']['interval']}")
            print(f"Actualización cada: {intervalo_actualizacion} segundos")
            print(f"Precio actual: {precio_actual:.2f}")
            print(f"Point of Control: {vrvp_data['poc_precio']:.2f}")
            print(f"Value Area Superior: {vrvp_data['va_superior']:.2f}")
            print(f"Distancia al área superior: {distancia_superior}")
            print(f"Value Area Inferior: {vrvp_data['va_inferior']:.2f}")
            print(f"Distancia al área inferior: {distancia_inferior}")
            print(f"\nSEÑAL: {señal}")
            print(f"Razón: {razón}")
            
            if señal == "VENTA":
                print("🚨 ¡SEÑAL DE VENTA! 🚨")
                guardar_en_csv("VENTA", precio_actual, vrvp_data['va_superior'], vrvp_data['va_inferior'])
            elif señal == "COMPRA":
                print("🚨 ¡SEÑAL DE COMPRA! 🚨")
                guardar_en_csv("COMPRA", precio_actual, vrvp_data['va_superior'], vrvp_data['va_inferior'])
            
            time.sleep(intervalo_actualizacion)  # Esperar el intervalo definido
            
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)  # Esperar 5 segundos en caso de error

def obtener_datos_binance():
    """Obtiene datos históricos de Binance usando la API pública"""
    endpoint = f"{BASE_URL}/klines"
    params = {
        'symbol': SYMBOL,
        'interval': INTERVAL,
        'limit': LOOKBACK_PERIOD
    }
    
    response = requests.get(endpoint, params=params)
    if response.status_code != 200:
        raise Exception("Error al obtener datos de Binance")
    
    klines = response.json()
    
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')
    
    # Convertir columnas relevantes a float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    return df 

def calcular_distancia_areas(precio_actual, va_superior, va_inferior):
    """Calcula qué tan lejos está el precio actual de las áreas superior e inferior en una escala del 1 al 11."""
    
    # Distancia a la área superior
    if precio_actual == va_superior:
        distancia_superior = 10  # Precio en el área superior
    elif precio_actual > va_superior:
        distancia_superior = 11  # Precio por encima del área superior
    else:
        # Calcular la distancia relativa entre el precio actual y el área superior
        rango_total = va_superior - va_inferior
        distancia_relativa_superior = (precio_actual - va_inferior) / rango_total  # Normalizar entre 0 y 1
        distancia_superior = round(1 + (distancia_relativa_superior * 9))  # Escala de 1 a 9

    # Distancia a la área inferior
    if precio_actual == va_inferior:
        distancia_inferior = 10  # Precio en el área inferior
    elif precio_actual < va_inferior:
        distancia_inferior = 11  # Precio por debajo del área inferior
    else:
        # Calcular la distancia relativa entre el precio actual y el área inferior
        rango_total = va_superior - va_inferior
        distancia_relativa_inferior = (va_superior - precio_actual) / rango_total  # Normalizar entre 0 y 1
        distancia_inferior = round(1 + (distancia_relativa_inferior * 9))  # Escala de 1 a 9

    return distancia_superior, distancia_inferior

if __name__ == "__main__":
    mostrar_datos_tiempo_real() 