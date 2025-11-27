import streamlit as st
import pandas as pd
import xmlrpc.client

st.set_page_config(page_title="Diagnóstico Odoo", layout="wide")
st.title("🔬 Escáner de Órdenes de Compra")

# 1. CARGAR CREDENCIALES (Esto soluciona el error de 'URL not defined')
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
            # Leer datos clave de la cabecera
            oc_data = models.execute_kw(DB, uid, PASSWORD, 'purchase.order', 'read', [ids_oc], 
                {'fields': ['name', 'state', 'partner_id', 'project_id', 'analytic_account_id']})
            
            st.subheader("1. Datos de Cabecera")
            st.json(oc_data)
            
            # B. BUSCAR LÍNEAS
            ids_lines = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'search', [[['order_id', 'in', ids_oc]]])
            
            if ids_lines:
                lines_data = models.execute_kw(DB, uid, PASSWORD, 'purchase.order.line', 'read', [ids_lines], 
                    {'fields': [
                        'name', 
                        'product_qty', 
                        'qty_received', 
                        'qty_invoiced', 
                        'price_unit',
                        'account_analytic_id',    # Campo viejo
                        'analytic_distribution'   # Campo nuevo (JSON)
                    ]})
                
                st.subheader("2. Datos de Líneas (Raw)")
                df = pd.DataFrame(lines_data)
                
                # Cálculo de pendiente para verificar
                df['PENDIENTE_CANTIDAD'] = df['product_qty'] - df['qty_invoiced']
                df['PENDIENTE_MONTO'] = df['PENDIENTE_CANTIDAD'] * df['price_unit']
                
                st.dataframe(df)
                
                st.info("Fíjate en la columna 'analytic_distribution' y en 'PENDIENTE_MONTO'.")
            else:
                st.warning("La orden existe pero no tiene líneas de productos.")
                
    except Exception as e:
        st.error(f"Error de conexión XML-RPC: {e}")
