import xmlrpc.client
import streamlit as st

try:
    URL = st.secrets["odoo"]["url"]
    DB = st.secrets["odoo"]["db"]
    USERNAME = st.secrets["odoo"]["username"]
    PASSWORD = st.secrets["odoo"]["password"]
except:
    # Fallback to direct values if secrets not available (for local testing via python command, secrets might not load)
    # But since we run this via run_command, we need to load secrets manually or assume environment.
    # Actually, we can just read the secrets.toml file directly if needed, or assume the user runs it with streamlit? 
    # No, 'streamlit run' is for apps.
    
    # Let's try to parse secrets.toml manually for this script since we are running it as a standalone script
    import toml
    try:
        secrets = toml.load(".streamlit/secrets.toml")
        URL = secrets["odoo"]["url"]
        DB = secrets["odoo"]["db"]
        USERNAME = secrets["odoo"]["username"]
        PASSWORD = secrets["odoo"]["password"]
    except:
        print("Could not load secrets.")
        exit()

common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common')
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object')

fields = models.execute_kw(DB, uid, PASSWORD, 'product.product', 'fields_get', [], {'attributes': ['string', 'type', 'name']})

possible_matches = []
for fname, fprops in fields.items():
    if 'marca' in fname.lower() or 'brand' in fname.lower() or 'marca' in fprops['string'].lower() or ('x_' in fname and 'marca' in fprops['string'].lower()):
        possible_matches.append((fname, fprops['string']))

print("Possible 'Marca' fields:")
for m in possible_matches:
    print(m)
