import streamlit as st
import pandas as pd
import xmlrpc.client

st.set_page_config(page_title="Diagnóstico Facturación", layout="wide")
st.title("🔬 Escáner de Facturación Estimada (x_facturas.proyectos)")

# 1. CREDENCIALES
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    st.success(f"Conectado a Odoo: {URL}")
except Exception as e:
    st.error(f"❌ Error config: {e}")
    st.stop()

# 2. BOTÓN DE ESCANEO
if st.button("📥 Descargar TODOS los registros de Facturación Estimada"):
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # Paso A: Verificar estructura del modelo (Opcional, para ver campos reales)
        try:
            fields_info = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'fields_get', [], {'attributes': ['string', 'type']})
            st.write("Campos detectados en el modelo:", list(fields_info.keys()))
        except Exception as e:
            st.warning(f"No se pudo leer la estructura de campos: {e}")

        # Paso B: Descargar datos
        # Traemos TODO sin filtro para ver qué existe
        ids = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'search', [[]])
        
        if not ids:
            st.error("El modelo 'x_facturas.proyectos' está vacío o no se tiene acceso.")
        else:
            st.success(f"Se encontraron {len(ids)} registros.")
            
            # Intentamos leer los campos que nos interesan
            campos_a_leer = [
                'x_name',                # Hito / Descripción
                'x_studio_field_sFPxe',  # Nombre del Proyecto (Vínculo)
                'x_monto',               # Monto (Confirmado por ti)
                'x_studio_facturado',    # Checkbox estado
                'create_date'            # Fecha creación
            ]
            
            data = models.execute_kw(DB, uid, PASSWORD, 'x_facturas.proyectos', 'read', [ids], {'fields': campos_a_leer})
            df = pd.DataFrame(data)
            
            st.subheader("📋 Tabla de Datos Crudos")
            st.dataframe(df)
            
            # Paso C: Análisis específico para tu proyecto
            st.divider()
            st.subheader("🔎 Prueba de Búsqueda Específica")
            
            texto_busqueda = st.text_input("Escribe parte del nombre del proyecto (ej: 2025-47):", value="2025-47")
            
            if texto_busqueda:
                # Filtramos el DF en Python para ver si coincide algo
                df_filtrado = df[df['x_studio_field_sFPxe'].astype(str).str.contains(texto_busqueda, case=False, na=False)]
                
                if not df_filtrado.empty:
                    st.success(f"✅ ¡SÍ hay coincidencias para '{texto_busqueda}'!")
                    st.dataframe(df_filtrado)
                    
                    # Suma de prueba
                    suma = df_filtrado[df_filtrado['x_studio_facturado'] == False]['x_monto'].sum()
                    st.metric("Suma Pendiente (según Python)", f"{suma:,.2f}")
                else:
                    st.error(f"❌ No hay ninguna fila que contenga el texto '{texto_busqueda}' en el campo de proyecto.")
                    st.info("Revisa la columna 'x_studio_field_sFPxe' en la tabla de arriba. Copia y pega el nombre EXACTO tal como sale ahí.")

    except Exception as e:
        st.error(f"Error técnico: {e}")
