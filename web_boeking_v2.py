import streamlit as st
import sqlite3
from datetime import datetime
from twilio.rest import Client

# === TWILIO (GEHEIMEN VIA STREAMLIT SECRETS) ===
TWILIO_SID = st.secrets["TWILIO_SID"]
TWILIO_AUTH_TOKEN = st.secrets["TWILIO_AUTH_TOKEN"]
TWILIO_PHONE = st.secrets["TWILIO_PHONE"]
WHATSAPP_FROM = st.secrets["WHATSAPP_FROM"]

try:
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
    TWILIO_KLAAR = True
except:
    TWILIO_KLAAR = False

# === DATABASE ===
def init_db():
    conn = sqlite3.connect('salon.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS klanten (
        id INTEGER PRIMARY KEY, naam TEXT, telefoon TEXT, email TEXT, voorkeur TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS afspraken (
        id INTEGER PRIMARY KEY, klant_id INTEGER, datum TEXT, tijd TEXT, behandeling TEXT, status TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

def zoek_afspraken(telefoon):
    conn = sqlite3.connect('salon.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT a.id, k.naam, k.telefoon, k.voorkeur, a.datum, a.tijd, a.behandeling 
        FROM afspraken a JOIN klanten k ON a.klant_id = k.id 
        WHERE k.telefoon = ? AND a.status = 'geboekt'
    ''', (telefoon,))
    afspraken = cursor.fetchall()
    conn.close()
    return afspraken

def annuleer_afspraak(afspraak_id):
    conn = sqlite3.connect('salon.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE afspraken SET status = 'geannuleerd' WHERE id = ?", (afspraak_id,))
    conn.commit()
    conn.close()

def verplaats_afspraak(afspraak_id, nieuwe_datum, nieuwe_tijd):
    conn = sqlite3.connect('salon.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM afspraken WHERE datum = ? AND tijd = ? AND status = 'geboekt' AND id != ?", 
                   (nieuwe_datum, nieuwe_tijd, afspraak_id))
    if cursor.fetchone():
        return False
    cursor.execute("UPDATE afspraken SET datum = ?, tijd = ? WHERE id = ?", 
                   (nieuwe_datum, nieuwe_tijd, afspraak_id))
    conn.commit()
    conn.close()
    return True

# === VERSTUUR BERICHT (SMS of WHATSAPP) ===
def stuur_bevestiging(naam, telefoon, voorkeur, datum, tijd, behandeling, actie="bevestigd"):
    if not TWILIO_KLAAR:
        return "SMS/WhatsApp uitgeschakeld"
    
    if actie == "bevestigd":
        bericht = f"Hallo {naam}, afspraak {actie} op {datum} om {tijd} voor {behandeling}. – Salon Voetjes"
    elif actie == "verplaatst":
        bericht = f"Hallo {naam}, je afspraak is {actie} naar {datum} om {tijd} voor {behandeling}. – Salon Voetjes"
    elif actie == "geannuleerd":
        bericht = f"Hallo {naam}, je afspraak op {datum} om {tijd} is {actie}. – Salon Voetjes"
    
    try:
        if voorkeur == "WhatsApp":
            client.messages.create(
                body=bericht,
                from_=WHATSAPP_FROM,
                to=f"whatsapp:{telefoon}"
            )
            return "WhatsApp verzonden!"
        else:  # SMS
            client.messages.create(
                body=bericht,
                from_=TWILIO_PHONE,
                to=telefoon
            )
            return "SMS verzonden!"
    except Exception as e:
        return f"Mislukt: {e}"

# === STREAMLIT APP ===
st.set_page_config(page_title="Pedicure Salon", page_icon="feet")

st.title("Pedicure Salon Voetjes & Teentjes")
st.markdown("**Boek of beheer je afspraak online!**")

page = st.sidebar.selectbox("Kies een pagina", ["Boeken", "Mijn Afspraken"])

if page == "Boeken":
    with st.form("boeking_form"):
        st.subheader("Nieuwe Afspraak")
        naam = st.text_input("Naam *")
        telefoon = st.text_input("Telefoonnummer (+32... of +31...) *")
        email = st.text_input("E-mail (optioneel)")
        voorkeur = st.radio("Bevestiging via *", ["SMS", "WhatsApp"], help="Verplicht kiezen!")
        datum = st.date_input("Datum *", min_value=datetime.today())
        tijd = st.time_input("Tijd *")
        behandeling = st.selectbox("Behandeling *", ["Basis pedicure", "Luxe pedicure", "Medische pedicure", "Gellak", "Voetmassage"])

        verzonden = st.form_submit_button("Boek Afspraak")

        if verzonden:
            if not naam or not telefoon or not voorkeur or not datum or not tijd:
                st.error("Vul alle verplichte velden in!")
            else:
                conn = sqlite3.connect('salon.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM klanten WHERE telefoon = ?", (telefoon,))
                klant = cursor.fetchone()
                if not klant:
                    cursor.execute("INSERT INTO klanten (naam, telefoon, email, voorkeur) VALUES (?, ?, ?, ?)", 
                                   (naam, telefoon, email, voorkeur))
                    klant_id = cursor.lastrowid
                else:
                    klant_id = klant[0]
                    # Update voorkeur
                    cursor.execute("UPDATE klanten SET voorkeur = ? WHERE id = ?", (voorkeur, klant_id))

                datum_str = datum.strftime("%Y-%m-%d")
                tijd_str = tijd.strftime("%H:%M")

                cursor.execute("SELECT id FROM afspraken WHERE datum = ? AND tijd = ? AND status = 'geboekt'", 
                               (datum_str, tijd_str))
                if cursor.fetchone():
                    st.error("Deze tijd is al bezet!")
                else:
                    cursor.execute("INSERT INTO afspraken (klant_id, datum, tijd, behandeling, status) VALUES (?, ?, ?, ?, 'geboekt')",
                                   (klant_id, datum_str, tijd_str, behandeling))
                    conn.commit()
                    conn.close()

                    resultaat = stuur_bevestiging(naam, telefoon, voorkeur, datum_str, tijd_str, behandeling, "bevestigd")
                    st.success(f"Afspraak geboekt! {resultaat}")

elif page == "Mijn Afspraken":
    st.subheader("Bekijk en beheer je afspraken")

    if 'telefoon' not in st.session_state:
        st.session_state['telefoon'] = ''

    st.session_state['telefoon'] = st.text_input("Jouw telefoonnummer *", value=st.session_state['telefoon'])

    if st.button("Zoek Afspraken"):
        telefoon = st.session_state['telefoon']
        if not telefoon:
            st.error("Vul je telefoonnummer in!")
        else:
            st.session_state['afspraken'] = zoek_afspraken(telefoon)
            st.session_state['searched'] = True

    if 'searched' in st.session_state and st.session_state['searched']:
        afspraken = st.session_state['afspraken']
        if not afspraken:
            st.info("Geen geboekte afspraken gevonden. Boek er een!")
        else:
            st.success(f"{len(afspraken)} afspraak(en) gevonden:")
            for a in afspraken:
                afspraak_id, naam, telefoon, voorkeur, datum, tijd, behandeling = a
                with st.expander(f"{datum} {tijd} – {behandeling} ({naam})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        actie = st.radio("Actie", ["Niets", "Annuleren", "Verplaatsen"], key=f"radio_{afspraak_id}")
                    with col2:
                        if actie == "Annuleren":
                            if st.button("Bevestig annuleren", key=f"ann_{afspraak_id}"):
                                annuleer_afspraak(afspraak_id)
                                stuur_bevestiging(naam, telefoon, voorkeur, datum, tijd, behandeling, "geannuleerd")
                                st.success("Afspraak geannuleerd!")
                                st.session_state['afspraken'] = zoek_afspraken(st.session_state['telefoon'])
                        elif actie == "Verplaatsen":
                            nieuwe_datum = st.date_input("Nieuwe datum", value=datetime.strptime(datum, "%Y-%m-%d").date(), key=f"nd_{afspraak_id}")
                            nieuwe_tijd = st.time_input("Nieuwe tijd", value=datetime.strptime(tijd, "%H:%M").time(), key=f"nt_{afspraak_id}")
                            if st.button("Bevestig verplaatsen", key=f"ver_{afspraak_id}"):
                                if verplaats_afspraak(afspraak_id, nieuwe_datum.strftime("%Y-%m-%d"), nieuwe_tijd.strftime("%H:%M")):
                                    stuur_bevestiging(naam, telefoon, voorkeur, 
                                                      nieuwe_datum.strftime("%Y-%m-%d"), nieuwe_tijd.strftime("%H:%M"), 
                                                      behandeling, "verplaatst")
                                    st.success("Afspraak verplaatst!")
                                    st.session_state['afspraken'] = zoek_afspraken(st.session_state['telefoon'])
                                else:
                                    st.error("Nieuwe tijd is bezet!")

st.markdown("---")
st.caption("Gemaakt door jouw pedicuresalon – 100% automatisch")