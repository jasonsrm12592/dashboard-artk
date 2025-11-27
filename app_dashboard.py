import streamlit as st
import pandas as pd
import xmlrpc.client

st.set_page_config(page_title="Diagnóstico Odoo", layout="wide")
st.title("🔬 Escáner de Órdenes de Compra (V2)")

# 1. CARGAR CREDENCIALES
try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
    st.success(f"Conectado a: {URL}")
except Exception as e:
    st.error(f"❌ Error cargando secretos: {e}")
    st.stop()

# 2. INTERFAZ DE BÚSQUEDA
oc_name = st.text_input("Escribe el nombre EXACTO de la OC:", value="OC-0020663")

if st.button("🔎 Escanear Orden"):
    try:
        common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
        uid = common.authenticate(DB, USERNAME, PASSWORD, {})
        models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')
        
        # A. BUSCAR CABECERA
        ids_oc = models.execute_kw(DB, uid, PASSWORD, 'purchase.order', 'search', [[['name', '=', oc_name]]])
        
        if not ids_oc:
            st.error("❌ No se encontró esa OC en Odoo.")
        else:
            # LEER CABECERA (Sin 'project_id' porque falló)
            # Buscamos 'account_analytic_id' que es el campo clásico de vínculo
            campos_cabecera = ['name', 'state', 'partner_id', 'currency_id']
            
            # Intentamos leer campos extra si existen, pero protegidos
            oc_data = models.execute_kw(DB, uid, PASSWORD, 'purchase.order', 'read', [ids_oc], {'fields': campos_cabecera})
            
            st.subheader("1. Datos de Cabecera")
            st.json(oc_data)
            
            # B. BUSCAR LÍNEAS
            ids_lines = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'search', [[['order_id', 'in', ids_oc]]])
            
            if ids_lines:
                # Leemos distribución analítica de las líneas (Aquí suele estar el secreto en Odoo 16/17)
                lines_data = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [ids_lines], 
                    {'fields': [
                        'name', 
                        'product_qty', 
                        'qty_invoiced', 
                        'price_unit',
                        'analytic_distribution'   # <--- EL CAMPO IMPORTANTE (JSON)
                    ]})
                
                st.subheader("2. Datos de Líneas (Análisis)")
                df = pd.DataFrame(lines_data)
                
                if not df.empty:
                    # Calcular pendiente
                    df['PENDIENTE_QTY'] = df['product_qty'] - df['qty_invoiced']
                    df['PENDIENTE_MONTO'] = df['PENDIENTE_QTY'] * df['price_unit']
                    
                    # Mostrar columnas clave
                    st.dataframe(df[['name', 'analytic_distribution', 'PENDIENTE_QTY', 'PENDIENTE_MONTO']])
                    
                    # Análisis del JSON
                    dist = df.iloc[0]['analytic_distribution']
                    st.info(f"Contenido crudo de 'analytic_distribution': {dist}")
                    st.caption("Si ves un número aquí (ej: '45': 100), ese '45' es el ID de la Cuenta Analítica que debemos buscar.")
                
            else:
                st.warning("La orden existe pero no tiene líneas de productos.")
                
    except Exception as e:
        st.error(f"Error técnico: {e}")
