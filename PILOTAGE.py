import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import io
import os
from pathlib import Path

# ═════════════════════════════════════════════════════════════════════
# CONFIGURATION DE LA PAGE
# ═════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="DATA PRO MAX - Pilotage BI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═════════════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ═════════════════════════════════════════════════════════════════════
SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "projets_bi.db"

@st.cache_resource
def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Table principale des projets avec nouveaux champs
    c.execute("""
        CREATE TABLE IF NOT EXISTS projets (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            departement       TEXT,
            libelle           TEXT,
            description       TEXT,
            frequence         TEXT,
            date_entree       TEXT,
            date_fin          TEXT,
            date_debut        TEXT    DEFAULT '',
            nature            TEXT,
            domaine           TEXT,
            statut            TEXT    DEFAULT 'NON COMMENCE',
            porteur           TEXT    DEFAULT 'NON ASSIGNE',
            priorite          TEXT    DEFAULT 'A DEFINIR',
            date_livraison    TEXT    DEFAULT '',
            admin_filled      INTEGER DEFAULT 0,
            validation_status TEXT    DEFAULT 'EN ATTENTE',
            validation_date   TEXT    DEFAULT '',
            email_demandeur   TEXT    DEFAULT '',
            commentaire_admin TEXT    DEFAULT '',
            historique        TEXT    DEFAULT '',
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des utilisateurs (demandeurs)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT UNIQUE,
            nom         TEXT,
            departement TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des notifications
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            projet_id  INTEGER,
            user_email TEXT,
            message    TEXT,
            statut     TEXT DEFAULT 'NON LU',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (projet_id) REFERENCES projets(id)
        )
    """)
    
    conn.commit()

init_db()

# ═════════════════════════════════════════════════════════════════════
# FONCTIONS DE BASE DE DONNÉES
# ═════════════════════════════════════════════════════════════════════

def load_data() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM projets ORDER BY id DESC", conn)
    return df

def add_projet(departement, libelle, description, frequence, date_fin, nature, domaine, email_demandeur):
    conn = get_connection()
    c = conn.cursor()
    historique = f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Demande créée par {email_demandeur}"
    c.execute("""
        INSERT INTO projets
        (departement, libelle, description, frequence, date_entree, date_fin,
         nature, domaine, email_demandeur, historique, validation_status)
        VALUES (?,?,?,?,?,?,?,?,?,?,'EN ATTENTE')
    """, (departement, libelle, description, frequence,
          datetime.today().strftime("%Y-%m-%d"),
          date_fin.strftime("%Y-%m-%d"), nature, domaine, email_demandeur, historique))
    
    projet_id = c.lastrowid
    
    # Créer une notification
    add_notification(projet_id, email_demandeur, 
                    f"Votre demande '{libelle}' a été créée avec succès et est en attente de validation.")
    
    conn.commit()
    return projet_id

def update_projet_user(id_sel, libelle, description, frequence, nature, domaine):
    conn = get_connection()
    c = conn.cursor()
    
    # Récupérer l'historique existant
    row = c.execute("SELECT historique FROM projets WHERE id=?", (id_sel,)).fetchone()
    historique = row[0] if row else ""
    historique += f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Demande modifiée par l'utilisateur"
    
    c.execute("""
        UPDATE projets SET
            libelle=?, description=?, frequence=?, nature=?, domaine=?,
            historique=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (libelle, description, frequence, nature, domaine, historique, id_sel))
    conn.commit()

def validate_projet_admin(id_sel, libelle, description, frequence, nature, domaine,
                         statut, porteur, priorite, date_livraison, commentaire_admin, date_debut=""):
    conn = get_connection()
    c = conn.cursor()
    
    # Récupérer l'email du demandeur et l'historique
    row = c.execute("SELECT email_demandeur, historique FROM projets WHERE id=?", (id_sel,)).fetchone()
    email_demandeur = row[0] if row else ""
    historique = row[1] if row else ""
    historique += f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Demande VALIDÉE par l'administrateur"
    historique += f"\n   → Porteur: {porteur}, Priorité: {priorite}, Statut: {statut}"
    if date_debut:
        historique += f"\n   → Date de début: {date_debut}"
    
    c.execute("""
        UPDATE projets SET
            libelle=?, description=?, frequence=?, nature=?, domaine=?,
            statut=?, porteur=?, priorite=?, date_livraison=?, date_debut=?,
            admin_filled=1, validation_status='VALIDEE', validation_date=?,
            commentaire_admin=?, historique=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (libelle, description, frequence, nature, domaine,
          statut, porteur, priorite, date_livraison, date_debut,
          datetime.now().strftime("%Y-%m-%d %H:%M"),
          commentaire_admin, historique, id_sel))
    
    # Créer une notification pour le demandeur
    add_notification(id_sel, email_demandeur,
                    f"Votre demande '{libelle}' a été VALIDÉE. Porteur assigné: {porteur}. Priorité: {priorite}.")
    
    conn.commit()

def update_statut_projet(id_sel, nouveau_statut, commentaire=""):
    conn = get_connection()
    c = conn.cursor()
    
    # Récupérer l'email du demandeur et l'historique
    row = c.execute("SELECT email_demandeur, historique, libelle FROM projets WHERE id=?", (id_sel,)).fetchone()
    email_demandeur = row[0] if row else ""
    historique = row[1] if row else ""
    libelle = row[2] if row else ""
    
    historique += f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Statut changé vers: {nouveau_statut}"
    if commentaire:
        historique += f"\n   → Commentaire: {commentaire}"
    
    c.execute("""
        UPDATE projets SET
            statut=?, historique=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (nouveau_statut, historique, id_sel))
    
    # Créer une notification
    add_notification(id_sel, email_demandeur,
                    f"Statut de votre demande '{libelle}' mis à jour: {nouveau_statut}")
    
    conn.commit()

def delete_projet(id_sel):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM projets WHERE id=?", (id_sel,))
    c.execute("DELETE FROM notifications WHERE projet_id=?", (id_sel,))
    conn.commit()

def add_notification(projet_id, user_email, message):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO notifications (projet_id, user_email, message, statut)
        VALUES (?, ?, ?, 'NON LU')
    """, (projet_id, user_email, message))
    conn.commit()

def get_user_notifications(email):
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT n.*, p.libelle as projet_libelle
        FROM notifications n
        LEFT JOIN projets p ON n.projet_id = p.id
        WHERE n.user_email = ?
        ORDER BY n.created_at DESC
    """, conn, params=(email,))
    return df

def mark_notifications_read(email):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE notifications SET statut='LU' WHERE user_email=?", (email,))
    conn.commit()

def get_user_demandes(email):
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT * FROM projets 
        WHERE email_demandeur = ?
        ORDER BY created_at DESC
    """, conn, params=(email,))
    return df

# ═════════════════════════════════════════════════════════════════════
# CONSTANTES
# ═════════════════════════════════════════════════════════════════════
DEPARTEMENTS   = ["OPERATIONS", "PMO", "MARKETING", "MARCHAND",
                  "DISTRIBUTION", "CONFORMITE", "RISQUES", "DG", "DGA", "SM MARKETING", "BI", "CORPORATE", "IT", "EXTERNE"]
FREQUENCES     = ["ADHOC", "JOURNALIERE", "HEBDOMADAIRE", "MENSUEL", "2 FOIS PAR SEMAINE", "2 FOIS PAR MOIS"]
NATURES        = ["EXTRACTION", "ANALYSE", "REPORTING", "DASHBOARD", "AUTRES"]
DOMAINES       = ["DISTRIBUTION", "MARCHAND", "CLIENT FINAL",
                  "PARTENAIRES", "INTERNE", "AUTRES"]
STATUTS        = ["NON COMMENCE", "EN COURS", "TERMINE"]
PORTEURS       = ["NON ASSIGNE", "CHRISTOL", "JINOR", "CYRILLE",
                  "DILANE", "SONIA"]
PRIORITES      = ["A DEFINIR", "DEPRIORISE", "P0", "P1", "P2", "P3", "P4"]
ADMIN_PASSWORD = "OMCMBI"

STATUT_COLORS  = {
    "NON COMMENCE": "#ef4444",
    "EN COURS"    : "#f59e0b",
    "TERMINE"     : "#10b981",
}

VALIDATION_COLORS = {
    "EN ATTENTE": "#f59e0b",
    "VALIDEE": "#10b981",
    "REJETEE": "#ef4444",
}

# ═════════════════════════════════════════════════════════════════════
# CSS GLOBAL AMÉLIORÉ - DATA PRO MAX STYLE
# ═════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --primary-light: #818cf8;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --info: #3b82f6;
    --dark: #1e293b;
    --light: #f8fafc;
}

html, body, [class*="css"] { 
    font-family: 'Inter', 'Poppins', sans-serif; 
}

/* HEADER MODERNE */
.main-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2.5rem 2rem;
    border-radius: 20px;
    margin-bottom: 2rem;
    box-shadow: 0 20px 60px rgba(102, 126, 234, 0.3);
    animation: fadeInDown 0.6s ease-out;
}

.main-header h1 {
    color: white;
    font-size: 3rem;
    font-weight: 900;
    margin: 0;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
    letter-spacing: -1px;
}

.main-header p {
    color: rgba(255,255,255,0.9);
    font-size: 1.1rem;
    margin-top: 0.5rem;
}

/* ANIMATIONS */
@keyframes fadeInDown {
    from {
        opacity: 0;
        transform: translateY(-30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes slideInRight {
    from {
        opacity: 0;
        transform: translateX(30px);
    }
    to {
        opacity: 1;
        transform: translateX(0);
    }
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.8; }
}

@keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
}

/* CARTES KPI ULTRA-MODERNES */
.kpi-card {
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border-radius: 20px;
    padding: 2rem;
    box-shadow: 0 10px 30px rgba(0,0,0,.08);
    border: 1px solid rgba(99, 102, 241, 0.1);
    position: relative;
    overflow: hidden;
    transition: all .4s cubic-bezier(0.4, 0, 0.2, 1);
    animation: fadeInUp 0.6s ease-out;
}

.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: linear-gradient(90deg, var(--primary) 0%, var(--primary-light) 100%);
    transform: scaleX(0);
    transform-origin: left;
    transition: transform 0.4s ease;
}

.kpi-card:hover::before {
    transform: scaleX(1);
}

.kpi-card:hover { 
    transform: translateY(-10px) scale(1.02); 
    box-shadow: 0 20px 50px rgba(99, 102, 241, 0.2);
    border-color: var(--primary);
}

.kpi-icon {
    font-size: 2.5rem;
    position: absolute;
    right: 1.5rem;
    top: 1.5rem;
    opacity: 0.15;
    transition: all 0.4s ease;
}

.kpi-card:hover .kpi-icon {
    opacity: 0.3;
    transform: scale(1.2) rotate(10deg);
}

.kpi-title { 
    font-size: 0.85rem; 
    font-weight: 700; 
    color: #64748b; 
    text-transform: uppercase; 
    letter-spacing: 0.1em; 
    margin-bottom: 0.8rem;
}

.kpi-value { 
    font-size: 3rem; 
    font-weight: 900; 
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0.5rem 0; 
    line-height: 1;
    animation: pulse 2s ease-in-out infinite;
}

.kpi-sub { 
    font-size: 0.9rem; 
    color: #94a3b8; 
    font-weight: 500;
    margin-top: 0.8rem;
}

/* BADGES STATUT MODERNES */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 8px 16px; 
    border-radius: 100px;
    font-size: 0.75rem; 
    font-weight: 700; 
    letter-spacing: 0.05em;
    text-transform: uppercase;
    box-shadow: 0 4px 12px rgba(0,0,0,.1);
    transition: all 0.3s ease;
    animation: slideInRight 0.5s ease-out;
}

.badge:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,.15);
}

.badge::before {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
    animation: pulse 2s ease-in-out infinite;
}

.badge-green  { background: linear-gradient(135deg, #d1fae5 0%, #a7f3d0 100%); color: #065f46; }
.badge-yellow { background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); color: #92400e; }
.badge-red    { background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%); color: #991b1b; }
.badge-blue   { background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%); color: #1e40af; }
.badge-gray   { background: linear-gradient(135deg, #f3f4f6 0%, #e5e7eb 100%); color: #374151; }
.badge-orange { background: linear-gradient(135deg, #ffedd5 0%, #fed7aa 100%); color: #9a3412; }

/* SIDEBAR ULTRA-MODERNE */
[data-testid="stSidebar"] { 
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    box-shadow: 4px 0 20px rgba(0,0,0,0.1);
}

[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}

[data-testid="stSidebar"] h3 {
    color: white !important;
    font-weight: 700;
    font-size: 1.1rem;
    margin-top: 1.5rem;
}

[data-testid="stSidebar"] .stRadio > label {
    font-weight: 600;
    color: white !important;
    font-size: 1rem;
}

[data-testid="stSidebar"] [data-baseweb="radio"] {
    background: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    margin: 0.3rem 0;
    transition: all 0.3s ease;
}

[data-testid="stSidebar"] [data-baseweb="radio"]:hover {
    background: rgba(99, 102, 241, 0.2);
    transform: translateX(5px);
}

/* BOUTONS MODERNES */
.stButton > button {
    border-radius: 12px;
    font-weight: 600;
    padding: 0.6rem 1.5rem;
    transition: all .3s cubic-bezier(0.4, 0, 0.2, 1);
    border: none;
    box-shadow: 0 4px 12px rgba(0,0,0,.1);
}

.stButton > button:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(99, 102, 241, 0.3);
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
}

/* FORMULAIRES ÉLÉGANTS - VISIBILITÉ AMÉLIORÉE */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stDateInput > div > div > input {
    border-radius: 12px;
    border: 2px solid #cbd5e1 !important;
    transition: all 0.3s ease;
    padding: 0.8rem;
    background-color: #ffffff !important;
    color: #1e293b !important;
    font-size: 1rem !important;
}

.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stDateInput > div > div > input:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2) !important;
}

/* SELECTBOX - VISIBILITÉ OPTIMALE */
.stSelectbox > div > div {
    border-radius: 12px !important;
    border: 2px solid #cbd5e1 !important;
    background-color: #ffffff !important;
}

.stSelectbox > div > div > div {
    background-color: #ffffff !important;
    color: #1e293b !important;
    font-size: 1rem !important;
    padding: 0.5rem !important;
}

.stSelectbox [data-baseweb="select"] > div {
    background-color: #ffffff !important;
    border-radius: 10px !important;
}

.stSelectbox [data-baseweb="select"] span {
    color: #1e293b !important;
    font-weight: 500 !important;
}

/* DROPDOWN MENU */
[data-baseweb="popover"] {
    background-color: #ffffff !important;
    border: 2px solid #e2e8f0 !important;
    border-radius: 12px !important;
    box-shadow: 0 10px 40px rgba(0,0,0,0.15) !important;
}

[data-baseweb="menu"] {
    background-color: #ffffff !important;
}

[data-baseweb="menu"] li {
    color: #1e293b !important;
    padding: 0.8rem 1rem !important;
}

[data-baseweb="menu"] li:hover {
    background-color: #f1f5f9 !important;
}

/* DATE INPUT SPECIAL */
.stDateInput > div > div > div > input {
    background-color: #ffffff !important;
    color: #1e293b !important;
    border: 2px solid #cbd5e1 !important;
    border-radius: 12px !important;
}

/* LABELS */
.stTextInput > label,
.stTextArea > label,
.stSelectbox > label,
.stDateInput > label,
.stMultiSelect > label {
    color: #334155 !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    margin-bottom: 0.5rem !important;
}

/* MULTISELECT */
.stMultiSelect > div > div {
    border-radius: 12px !important;
    border: 2px solid #cbd5e1 !important;
    background-color: #ffffff !important;
}

.stMultiSelect [data-baseweb="tag"] {
    background-color: #6366f1 !important;
    color: white !important;
    border-radius: 8px !important;
}

/* TABLEAUX MODERNES */
[data-testid="stDataFrame"] {
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 8px 24px rgba(0,0,0,.08);
    border: 1px solid #e2e8f0;
}

/* ONGLETS STYLÉS */
.stTabs [data-baseweb="tab-list"] {
    gap: 12px;
    background: #f8fafc;
    padding: 0.8rem;
    border-radius: 16px;
    box-shadow: inset 0 2px 8px rgba(0,0,0,0.05);
}

.stTabs [data-baseweb="tab"] {
    border-radius: 12px;
    font-weight: 600;
    padding: 0.8rem 1.8rem;
    transition: all 0.3s ease;
}

.stTabs [data-baseweb="tab"]:hover {
    background: rgba(99, 102, 241, 0.1);
}

.stTabs [data-baseweb="tab"][aria-selected="true"] {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    color: white;
}

/* BARRE DE PROGRESSION ANIMÉE */
.stProgress > div > div > div > div { 
    background: linear-gradient(90deg, #10b981 0%, #059669 100%);
    height: 16px;
    border-radius: 100px;
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
    animation: pulse 2s ease-in-out infinite;
}

/* CONTENEURS */
.stContainer {
    animation: fadeInUp 0.6s ease-out;
}

/* EXPANDER */
.streamlit-expanderHeader {
    border-radius: 12px;
    background: #f8fafc;
    font-weight: 600;
    transition: all 0.3s ease;
}

.streamlit-expanderHeader:hover {
    background: #e2e8f0;
}

/* DIVIDER ÉLÉGANT */
hr {
    border: none;
    height: 2px;
    background: linear-gradient(90deg, transparent 0%, var(--primary) 50%, transparent 100%);
    margin: 2rem 0;
}

/* METRICS */
[data-testid="stMetricValue"] {
    font-size: 2.5rem;
    font-weight: 800;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* ALERTES MODERNES */
.stAlert {
    border-radius: 16px;
    border-left: 4px solid;
    animation: slideInRight 0.5s ease-out;
}

/* FOOTER */
.footer-text {
    text-align: center;
    color: #94a3b8;
    padding: 3rem 2rem;
    font-weight: 500;
}

/* RESPONSIVE */
@media (max-width: 768px) {
    .kpi-value { font-size: 2rem; }
    .main-header h1 { font-size: 2rem; }
}

/* SCROLLBAR PERSONNALISÉE */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

::-webkit-scrollbar-track {
    background: #f1f5f9;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
    border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--primary-dark);
}
</style>
""", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═════════════════════════════════════════════════════════════════════

def safe_index(lst, val, default=0):
    try:
        return lst.index(val)
    except (ValueError, AttributeError):
        return default

def format_date(date_str):
    try:
        date_obj = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return date_obj.strftime("%d/%m/%Y")
    except:
        return date_str

def get_status_color(statut):
    colors = {
        "NON COMMENCE": "red",
        "EN COURS": "orange",
        "TERMINE": "green"
    }
    return colors.get(statut, "gray")

def get_validation_color(validation_status):
    colors = {
        "EN ATTENTE": "orange",
        "VALIDEE": "green",
        "REJETEE": "red"
    }
    return colors.get(validation_status, "gray")

def get_priority_color(priorite):
    priority_colors = {
        "P0": "red",
        "P1": "red",
        "P2": "orange",
        "P3": "blue",
        "P4": "blue",
        "DEPRIORISE": "gray",
        "A DEFINIR": "gray"
    }
    return priority_colors.get(priorite, "gray")

def render_kpi_card(title, value, subtitle, icon, color="#6366f1"):
    """Render a modern KPI card with icon and animations"""
    st.markdown(f"""
    <div class="kpi-card">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-title">{title}</div>
        <div class="kpi-value" style="background: linear-gradient(135deg, {color} 0%, {color}dd 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{value}</div>
        <div class="kpi-sub">{subtitle}</div>
    </div>
    """, unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════
# EN-TÊTE MODERNE AVEC LOGO
# ═════════════════════════════════════════════════════════════════════
def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>📊 DATA PRO MAX</h1>
        <p>Système de pilotage intelligent des demandes BI · Orange Money</p>
    </div>
    """, unsafe_allow_html=True)

render_header()

# ═════════════════════════════════════════════════════════════════════
# SESSION STATE POUR L'AUTHENTIFICATION UTILISATEUR
# ═════════════════════════════════════════════════════════════════════
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = 'user'

# ═════════════════════════════════════════════════════════════════════
# SIDEBAR MODERNE
# ═════════════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo Orange Money en haut de la sidebar
    import base64
    logo_path = SCRIPT_DIR / "assets" / "logo_orange_money.png"
    if logo_path.exists():
        with open(logo_path, "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()
        st.markdown(f'''
        <div style="text-align: center; padding: 1rem 0 1.5rem 0;">
            <img src="data:image/png;base64,{logo_data}" alt="Orange Money" style="max-width: 150px; height: auto;">
        </div>
        ''', unsafe_allow_html=True)
    
    st.markdown("### 👤 Identification")
    
    # Saisie de l'email utilisateur
    if st.session_state.user_email is None:
        user_email = st.text_input("Votre email professionnel", 
                                   placeholder="prenom.nom@orangemoney.com")
        user_dept = st.selectbox("Votre département", DEPARTEMENTS)
        
        if st.button("🔐 Se connecter", use_container_width=True):
            if user_email and "@" in user_email:
                st.session_state.user_email = user_email
                st.session_state.user_dept = user_dept
                st.rerun()
            else:
                st.error("Veuillez entrer un email valide")
    else:
        st.success(f"✅ Connecté: {st.session_state.user_email}")
        
        # Afficher les notifications non lues
        notif_df = get_user_notifications(st.session_state.user_email)
        unread_count = len(notif_df[notif_df['statut'] == 'NON LU'])
        
        if unread_count > 0:
            st.warning(f"🔔 {unread_count} notification(s) non lue(s)")
        
        if st.button("🚪 Déconnexion", use_container_width=True):
            st.session_state.user_email = None
            st.session_state.user_role = 'user'
            st.rerun()
    
    st.divider()
    
    if st.session_state.user_email:
        st.markdown("### 📍 Navigation")
        menu = st.radio(
            "",
            ["📊 Tableau de bord", 
             "🎯 Mes demandes",
             "🔔 Notifications",
             "📂 Dossier en attente",
             "📋 Registre des demandes", 
             "➕ Nouvelle demande"],
            label_visibility="collapsed"
        )
    else:
        menu = None
        st.info("👆 Connectez-vous pour accéder à l'application")
    
    st.divider()
    st.caption("🏢 Orange Money · Département BI")
    st.caption("DATA PRO MAX v2.0 · Usage Interne")

# ═════════════════════════════════════════════════════════════════════
# VÉRIFICATION DE LA CONNEXION
# ═════════════════════════════════════════════════════════════════════
if st.session_state.user_email is None:
    st.info("👈 Veuillez vous connecter avec votre email professionnel pour accéder à l'application.")
    st.stop()

# ═════════════════════════════════════════════════════════════════════
# PAGE : NOUVELLE DEMANDE
# ═════════════════════════════════════════════════════════════════════
if menu == "➕ Nouvelle demande":
    st.header("➕ Créer une nouvelle demande")
    
    st.info("""
    📝 **Informations importantes**
    - ✅ Votre demande sera **enregistrée avec votre email**
    - ⏳ Elle sera **en attente de validation** par l'administrateur
    - 📧 Vous recevrez des **notifications** à chaque changement de statut
    - 👁️ Vous pourrez **suivre sa progression** dans "Mes demandes"
    """)
    
    with st.form("form_projet", clear_on_submit=True):
        st.subheader("📋 Détails de la demande")
        
        col1, col2 = st.columns(2)
        with col1:
            departement = st.selectbox("Département *", DEPARTEMENTS, 
                                      index=safe_index(DEPARTEMENTS, st.session_state.get('user_dept', '')))
            libelle = st.text_input("Libellé (titre court) *", max_chars=100,
                                   placeholder="Ex: Rapport mensuel des ventes")
            description = st.text_area("Description détaillée *", max_chars=500,
                                      placeholder="Décrivez précisément votre besoin...",
                                      height=150)
        with col2:
            frequence = st.selectbox("Fréquence de production", FREQUENCES)
            nature = st.selectbox("Nature de la demande", NATURES)
            domaine = st.selectbox("Domaine fonctionnel", DOMAINES)
            date_fin = st.date_input("Date de fin souhaitée *",
                                    min_value=datetime.today())
        
        st.divider()
        submitted = st.form_submit_button("✅ Soumettre la demande",
                                         use_container_width=True,
                                         type="primary")
        
        if submitted:
            if libelle.strip() and description.strip():
                projet_id = add_projet(
                    departement, libelle.strip(), description.strip(),
                    frequence, date_fin, nature, domaine, 
                    st.session_state.user_email
                )
                st.success(f"✅ Demande #{projet_id} créée avec succès !")
                st.info("📧 Vous recevrez une notification dès qu'elle sera traitée par l'administrateur.")
                st.balloons()
            else:
                st.error("❌ Le libellé et la description sont obligatoires.")

# ═════════════════════════════════════════════════════════════════════
# PAGE : MES DEMANDES (SUIVI UTILISATEUR)
# ═════════════════════════════════════════════════════════════════════
elif menu == "🎯 Mes demandes":
    st.header("🎯 Mes demandes en cours")
    
    user_demandes = get_user_demandes(st.session_state.user_email)
    
    if user_demandes.empty:
        st.info("📭 Vous n'avez aucune demande enregistrée pour le moment.")
        st.markdown("💡 **Créez votre première demande** en cliquant sur '➕ Nouvelle demande' dans le menu.")
    else:
        # Statistiques personnelles
        col1, col2, col3, col4 = st.columns(4)
        
        total_demandes = len(user_demandes)
        en_attente = len(user_demandes[user_demandes['validation_status'] == 'EN ATTENTE'])
        validees = len(user_demandes[user_demandes['validation_status'] == 'VALIDEE'])
        terminees = len(user_demandes[user_demandes['statut'] == 'TERMINE'])
        
        with col1:
            render_kpi_card("Total", total_demandes, "demandes", "📦", "#3b82f6")
        with col2:
            render_kpi_card("En attente", en_attente, "validation", "⏳", "#f59e0b")
        with col3:
            render_kpi_card("Validées", validees, "en cours", "✅", "#10b981")
        with col4:
            render_kpi_card("Terminées", terminees, "livrées", "👍", "#10b981")
        
        st.divider()
        
        # Filtre de statut
        filtre_validation = st.multiselect(
            "Filtrer par statut de validation",
            ["EN ATTENTE", "VALIDEE", "REJETEE"],
            default=["EN ATTENTE", "VALIDEE"]
        )
        
        filtered_demandes = user_demandes[user_demandes['validation_status'].isin(filtre_validation)]
        
        # Affichage des demandes
        for _, row in filtered_demandes.iterrows():
            with st.container():
                st.subheader(f"📦 {row['libelle']}")
                
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.caption(f"Demande #{row['id']} · {row['departement']}")
                with col2:
                    val_color = get_validation_color(row['validation_status'])
                    st.markdown(f":{val_color}[{row['validation_status']}]")
                with col3:
                    stat_color = get_status_color(row['statut'])
                    st.markdown(f":{stat_color}[{row['statut']}]")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"📅 **Date de création:** {format_date(row['date_entree'])}")
                    st.write(f"📊 **Nature:** {row['nature']}")
                with col2:
                    st.write(f"🗂️ **Domaine:** {row['domaine']}")
                    st.write(f"⏱️ **Fréquence:** {row['frequence']}")
                
                # Afficher les infos supplémentaires si validé
                if row['validation_status'] == 'VALIDEE':
                    st.write(f"👤 **Porteur assigné:** {row['porteur']}")
                    st.write(f"⭐ **Priorité:** {row['priorite']}")
                    
                    if row.get('date_debut') and row['date_debut']:
                        st.write(f"🚀 **Date de début:** {format_date(row['date_debut'])}")
                    
                    if row['date_livraison']:
                        st.write(f"📆 **Date de livraison prévue:** {format_date(row['date_livraison'])}")
                    
                    if row['commentaire_admin']:
                        st.info(f"💬 **Commentaire admin:** {row['commentaire_admin']}")
                
                # Expander pour l'historique
                with st.expander(f"📜 Historique de la demande #{row['id']}"):
                    if row['historique']:
                        historique_lines = row['historique'].split('\n')
                        for line in historique_lines:
                            if line.strip():
                                st.write(f"• {line}")
                    else:
                        st.info("Aucun historique disponible")
                
                st.divider()

# ═════════════════════════════════════════════════════════════════════
# PAGE : NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════
elif menu == "🔔 Notifications":
    st.header("🔔 Mes notifications")
    
    notif_df = get_user_notifications(st.session_state.user_email)
    
    if notif_df.empty:
        st.info("📭 Aucune notification pour le moment.")
    else:
        # Bouton pour marquer toutes comme lues
        if st.button("✅ Marquer toutes comme lues"):
            mark_notifications_read(st.session_state.user_email)
            st.success("Notifications marquées comme lues")
            st.rerun()
        
        st.divider()
        
        # Afficher les notifications
        for _, notif in notif_df.iterrows():
            is_unread = notif['statut'] == 'NON LU'
            
            with st.container():
                col1, col2 = st.columns([4, 1])
                with col1:
                    projet_label = notif['projet_libelle'] or 'Demande'
                    if is_unread:
                        st.markdown(f"**📦 {projet_label}** 🔴 NOUVEAU")
                    else:
                        st.markdown(f"📦 {projet_label}")
                    st.write(notif['message'])
                with col2:
                    st.caption(format_date(str(notif['created_at'])[:10]))
                st.divider()

# ═════════════════════════════════════════════════════════════════════
# PAGE : DOSSIER EN ATTENTE (Admin uniquement avec validation complète)
# ═════════════════════════════════════════════════════════════════════
elif menu == "📂 Dossier en attente":
    st.header("📂 Dossier en attente de validation")
    
    # Vérification du mot de passe admin
    with st.expander("🔐 Accès Administrateur", expanded=True):
        admin_pwd = st.text_input("Mot de passe administrateur", type="password", key="admin_access")
        if st.button("🔓 Accéder"):
            if admin_pwd == ADMIN_PASSWORD:
                st.session_state.user_role = 'admin'
                st.success("✅ Accès administrateur accordé")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect")
    
    if st.session_state.user_role != 'admin':
        st.warning("🔒 Cette section est réservée aux administrateurs. Veuillez vous authentifier.")
        st.stop()
    
    df = load_data()
    pending = df[df["validation_status"] == "EN ATTENTE"].copy()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        render_kpi_card("En attente", len(pending), "validation", "⏳", "#f59e0b")
    with col2:
        render_kpi_card("Total", len(df), "demandes", "📦", "#3b82f6")
    with col3:
        taux = (len(df)-len(pending))/len(df)*100 if len(df)>0 else 0
        render_kpi_card("Traitement", f"{taux:.1f}%", "complétées", "✅", "#10b981")
    
    st.divider()
    
    if pending.empty:
        st.success("🎉 Toutes les demandes ont été traitées !")
    else:
        st.warning(f"⚠️ {len(pending)} demande(s) nécessite(nt) une validation administrative.")
        
        # Tableau des demandes en attente
        display_cols = ['id', 'libelle', 'departement', 'email_demandeur', 'date_entree', 'nature', 'domaine']
        st.dataframe(pending[display_cols], use_container_width=True, hide_index=True)
        
        st.divider()
        st.subheader("✏️ Valider une demande")
        
        # Sélection de la demande à valider
        id_to_validate = st.selectbox("Sélectionner l'ID de la demande à valider", 
                                      pending['id'].tolist())
        
        if id_to_validate:
            row = pending[pending['id'] == id_to_validate].iloc[0]
            
            st.info(f"""
            **📦 {row['libelle']}** (Demande #{row['id']})
            - 📧 Demandeur: {row['email_demandeur']}
            - 🏢 Département: {row['departement']}
            - 📝 Description: {row['description']}
            """)
            
            with st.form("validation_form"):
                st.subheader("🔐 Validation administrative")
                
                col1, col2 = st.columns(2)
                with col1:
                    n_libelle = st.text_input("Libellé", value=row['libelle'])
                    n_nature = st.selectbox("Nature", NATURES,
                                          index=safe_index(NATURES, row['nature']))
                    n_statut = st.selectbox("Statut initial", STATUTS,
                                          index=safe_index(STATUTS, row['statut']))
                    n_porteur = st.selectbox("Porteur assigné *", PORTEURS)
                    n_date_debut = st.date_input("📅 Date de début *", value=datetime.today(),
                                                help="Date à laquelle le travail sur cette demande doit commencer")
                
                with col2:
                    n_description = st.text_area("Description", value=row['description'], height=100)
                    n_domaine = st.selectbox("Domaine", DOMAINES,
                                           index=safe_index(DOMAINES, row['domaine']))
                    n_priorite = st.selectbox("Priorité *", PRIORITES)
                    try:
                        default_date = datetime.strptime(row['date_livraison'], "%Y-%m-%d") if row['date_livraison'] else datetime.today()
                    except:
                        default_date = datetime.today()
                    n_date_livraison = st.date_input("Date de livraison prévue", value=default_date)
                
                n_frequence = st.selectbox("Fréquence", FREQUENCES,
                                         index=safe_index(FREQUENCES, row['frequence']))
                n_commentaire = st.text_area("Commentaire pour le demandeur", 
                                            placeholder="Ajoutez des précisions ou instructions...",
                                            height=100)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    validate_btn = st.form_submit_button("✅ VALIDER LA DEMANDE", 
                                                        use_container_width=True,
                                                        type="primary")
                with col_btn2:
                    cancel_btn = st.form_submit_button("❌ Annuler", use_container_width=True)
                
                if validate_btn:
                    if n_porteur != "NON ASSIGNE" and n_priorite != "A DEFINIR":
                        validate_projet_admin(
                            id_to_validate, n_libelle, n_description, n_frequence,
                            n_nature, n_domaine, n_statut, n_porteur, n_priorite,
                            n_date_livraison.strftime("%Y-%m-%d"), n_commentaire,
                            n_date_debut.strftime("%Y-%m-%d")
                        )
                        st.success(f"✅ Demande #{id_to_validate} validée avec succès !")
                        st.info(f"📧 Notification envoyée à {row['email_demandeur']}")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("❌ Veuillez assigner un porteur et définir une priorité pour valider la demande.")
        
        # Export Excel
        excel_buf = io.BytesIO()
        pending[display_cols].to_excel(excel_buf, index=False)
        excel_buf.seek(0)
        st.download_button(
            "📥 Exporter les demandes en attente (Excel)",
            data=excel_buf,
            file_name=f"demandes_en_attente_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

# ═════════════════════════════════════════════════════════════════════
# PAGE : REGISTRE DES DEMANDES
# ═════════════════════════════════════════════════════════════════════
elif menu == "📋 Registre des demandes":
    st.header("📋 Registre complet des demandes")
    df = load_data()
    
    # Ne montrer QUE les demandes validées dans le registre
    df_validated = df[df['validation_status'] == 'VALIDEE'].copy()
    
    if df_validated.empty:
        st.info("📭 Aucune demande validée pour le moment.")
        st.stop()
    
    tab_view, tab_edit, tab_delete = st.tabs(
        ["👁️ Vue d'ensemble", "✏️ Modifier", "🗑️ Supprimer"]
    )
    
    with tab_view:
        st.subheader("🔍 Filtres avancés")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            f_dept = st.multiselect("Département", DEPARTEMENTS)
        with col2:
            f_stat = st.multiselect("Statut", STATUTS)
        with col3:
            f_prio = st.multiselect("Priorité", PRIORITES)
        with col4:
            f_porteur = st.multiselect("Porteur", PORTEURS)
        
        fdf = df_validated.copy()
        if f_dept: fdf = fdf[fdf["departement"].isin(f_dept)]
        if f_stat: fdf = fdf[fdf["statut"].isin(f_stat)]
        if f_prio: fdf = fdf[fdf["priorite"].isin(f_prio)]
        if f_porteur: fdf = fdf[fdf["porteur"].isin(f_porteur)]
        
        st.dataframe(fdf, use_container_width=True, hide_index=True)
        st.caption(f"📊 {len(fdf)} demande(s) affichée(s) sur {len(df_validated)} validée(s)")
        
        # Export Excel
        excel_buf = io.BytesIO()
        fdf.to_excel(excel_buf, index=False)
        excel_buf.seek(0)
        st.download_button(
            "📥 Exporter la sélection (Excel)",
            data=excel_buf,
            file_name=f"registre_demandes_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    
    with tab_edit:
        st.subheader("✏️ Modifier une demande")
        
        if df_validated.empty:
            st.info("Aucune demande validée à modifier.")
        else:
            ids = df_validated["id"].tolist()
            id_sel = st.selectbox("Sélectionner l'ID de la demande", ids)
            row = df_validated[df_validated["id"] == id_sel].iloc[0]
            
            with st.form("edit_form"):
                col1, col2 = st.columns(2)
                with col1:
                    n_libelle = st.text_input("Libellé", value=row["libelle"])
                    n_desc = st.text_area("Description", value=row["description"])
                    n_freq = st.selectbox("Fréquence", FREQUENCES,
                                        index=safe_index(FREQUENCES, row["frequence"]))
                    n_nature = st.selectbox("Nature", NATURES,
                                          index=safe_index(NATURES, row["nature"]))
                with col2:
                    n_domaine = st.selectbox("Domaine", DOMAINES,
                                           index=safe_index(DOMAINES, row["domaine"]))
                    n_statut = st.selectbox("Statut", STATUTS,
                                          index=safe_index(STATUTS, row["statut"]))
                    n_porteur = st.selectbox("Porteur", PORTEURS,
                                           index=safe_index(PORTEURS, row["porteur"]))
                    n_prio = st.selectbox("Priorité", PRIORITES,
                                        index=safe_index(PRIORITES, row["priorite"]))
                
                col_dates = st.columns(2)
                with col_dates[0]:
                    try:
                        debut_date = datetime.strptime(row["date_debut"], "%Y-%m-%d") if row.get("date_debut") and row["date_debut"] else datetime.today()
                    except:
                        debut_date = datetime.today()
                    n_date_debut = st.date_input("📅 Date de début", value=debut_date)
                with col_dates[1]:
                    try:
                        dl_date = datetime.strptime(row["date_livraison"], "%Y-%m-%d") if row["date_livraison"] else datetime.today()
                    except:
                        dl_date = datetime.today()
                    n_date_liv = st.date_input("Date de livraison", value=dl_date)
                
                n_commentaire = st.text_area("Commentaire admin", value=row.get("commentaire_admin", ""))
                
                st.warning("🔐 Authentification requise")
                pwd = st.text_input("Mot de passe Admin *", type="password")
                
                if st.form_submit_button("💾 Enregistrer les modifications", use_container_width=True, type="primary"):
                    if pwd == ADMIN_PASSWORD:
                        validate_projet_admin(id_sel, n_libelle, n_desc, n_freq,
                                            n_nature, n_domaine, n_statut,
                                            n_porteur, n_prio,
                                            n_date_liv.strftime("%Y-%m-%d"), n_commentaire,
                                            n_date_debut.strftime("%Y-%m-%d"))
                        st.success("✅ Demande mise à jour avec succès !")
                        st.rerun()
                    else:
                        st.error("❌ Mot de passe administrateur incorrect")
    
    with tab_delete:
        st.warning("⚠️ **Action irréversible** — Réservée aux administrateurs uniquement")
        
        if df_validated.empty:
            st.info("Aucune demande à supprimer.")
        else:
            id_del = st.selectbox("ID de la demande à supprimer", df_validated["id"].tolist(), key="del_sel")
            
            # Afficher les détails de la demande
            row_del = df_validated[df_validated["id"] == id_del].iloc[0]
            st.error(f"""
            **⚠️ Demande à supprimer:**
            - **#{row_del['id']}** - {row_del['libelle']}
            - 📧 Demandeur: {row_del['email_demandeur']}
            - 🏢 Département: {row_del['departement']}
            """)
            
            pwd_del = st.text_input("Mot de passe Admin pour confirmer", type="password", key="del_pwd")
            
            if st.button("🗑️ SUPPRIMER DÉFINITIVEMENT", type="primary", use_container_width=True):
                if pwd_del == ADMIN_PASSWORD:
                    delete_projet(id_del)
                    st.success(f"✅ Demande #{id_del} supprimée.")
                    st.rerun()
                else:
                    st.error("❌ Mot de passe incorrect.")

# ═════════════════════════════════════════════════════════════════════
# PAGE : TABLEAU DE BORD (UNIQUEMENT DEMANDES VALIDÉES) - GRAPHIQUES AMÉLIORÉS
# ═════════════════════════════════════════════════════════════════════
elif menu == "📊 Tableau de bord":
    st.header("📊 Tableau de bord analytique")
    
    df_raw = load_data()
    
    # FILTRE CRITIQUE : Ne montrer QUE les demandes VALIDÉES
    df_validated = df_raw[df_raw['validation_status'] == 'VALIDEE'].copy()
    
    if df_validated.empty:
        st.info("📊 Aucune demande validée pour le moment. Le tableau de bord sera disponible dès qu'une demande sera validée par l'administrateur.")
        st.stop()
    
    # Filtre départemental
    st.subheader("🎯 Filtres de vue")
    dept_options = ["TOUS"] + sorted(DEPARTEMENTS)
    selected_dept = st.selectbox("Département", dept_options)
    
    if selected_dept == "TOUS":
        df = df_validated.copy()
        view_title = "📊 Vue Globale - Toutes les demandes validées"
    else:
        df = df_validated[df_validated["departement"] == selected_dept].copy()
        view_title = f"📊 Vue Département : {selected_dept}"
    
    st.subheader(view_title)
    
    if df.empty:
        st.warning(f"Aucune demande validée pour le département {selected_dept}.")
        st.stop()
    
    # KPIs avec nouveau design
    total = len(df)
    termines = len(df[df["statut"] == "TERMINE"])
    en_cours = len(df[df["statut"] == "EN COURS"])
    non_commence = len(df[df["statut"] == "NON COMMENCE"])
    progress = termines / total if total > 0 else 0
    
    k1, k2, k3, k4 = st.columns(4)
    
    with k1:
        render_kpi_card("Total Validé", total, "demandes en production", "📦", "#3b82f6")
    with k2:
        render_kpi_card("Terminées", termines, f"{progress:.0%} complétion", "✅", "#10b981")
    with k3:
        render_kpi_card("En cours", en_cours, "actives", "⏳", "#f59e0b")
    with k4:
        render_kpi_card("Non commencé", non_commence, "à démarrer", "🔴", "#ef4444")
    
    st.divider()
    
    # Barre de progression animée
    st.subheader(f"📈 Progression globale : {progress:.0%}")
    st.progress(progress)
    
    st.divider()
    
    # GRAPHIQUES AMÉLIORÉS AVEC ÉTIQUETTES DE VALEURS
    g1, g2 = st.columns(2)
    
    with g1:
        st.subheader("🍩 Répartition par statut")
        statut_counts = df['statut'].value_counts().reset_index()
        statut_counts.columns = ['statut', 'count']
        
        fig_pie = px.pie(
            statut_counts, 
            names="statut", 
            values="count",
            hole=0.5,
            color="statut",
            color_discrete_map=STATUT_COLORS,
        )
        fig_pie.update_traces(
            textposition="inside", 
            textinfo="percent+label+value",
            textfont_size=16,
            textfont_color="white",
            textfont_family="Inter",
            marker=dict(line=dict(color='white', width=3))
        )
        fig_pie.update_layout(
            showlegend=True, 
            margin=dict(t=20, b=20, l=20, r=20),
            font=dict(family="Inter", size=14),
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with g2:
        st.subheader("👥 Charge par porteur")
        porteur_statut = df.groupby(['porteur', 'statut']).size().reset_index(name='count')
        
        fig_bar = px.bar(
            porteur_statut, 
            x="porteur", 
            y="count",
            color="statut",
            color_discrete_map=STATUT_COLORS,
            barmode="stack",
            text="count"
        )
        fig_bar.update_traces(
            textposition="inside",
            textfont_size=14,
            textfont_color="white",
            textfont_family="Inter"
        )
        fig_bar.update_layout(
            xaxis_title="Porteur", 
            yaxis_title="Nombre de demandes",
            legend_title="Statut", 
            margin=dict(t=20),
            showlegend=True,
            font=dict(family="Inter", size=14),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
        )
        fig_bar.update_xaxes(showgrid=False)
        fig_bar.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
        st.plotly_chart(fig_bar, use_container_width=True)
    
    g3, g4 = st.columns(2)
    
    with g3:
        if selected_dept == "TOUS":
            st.subheader("🏢 Demandes par département")
            dept_df = df.groupby(["departement", "statut"]).size().reset_index(name="count")
            fig_dept = px.bar(
                dept_df, 
                x="count", 
                y="departement", 
                color="statut",
                color_discrete_map=STATUT_COLORS,
                orientation="h", 
                barmode="stack",
                text="count"
            )
            fig_dept.update_traces(
                textposition="inside",
                textfont_size=11,
                textfont_color="white",
                textfont_family="Inter"
            )
            fig_dept.update_layout(
                yaxis_title="", 
                xaxis_title="Nombre de demandes", 
                margin=dict(t=20),
                font=dict(family="Inter", size=14),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
            )
            fig_dept.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
            fig_dept.update_yaxes(showgrid=False)
            st.plotly_chart(fig_dept, use_container_width=True)
        else:
            st.subheader("🎯 Répartition par domaine")
            dom_df = df.groupby(["domaine", "statut"]).size().reset_index(name="count")
            fig_dom = px.bar(
                dom_df, 
                x="count", 
                y="domaine", 
                color="statut",
                color_discrete_map=STATUT_COLORS,
                orientation="h", 
                barmode="stack",
                text="count"
            )
            fig_dom.update_traces(
                textposition="inside",
                textfont_size=11,
                textfont_color="white",
                textfont_family="Inter"
            )
            fig_dom.update_layout(
                yaxis_title="", 
                xaxis_title="Nombre", 
                margin=dict(t=20),
                font=dict(family="Inter", size=14),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
            )
            fig_dom.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
            fig_dom.update_yaxes(showgrid=False)
            st.plotly_chart(fig_dom, use_container_width=True)
    
    with g4:
        st.subheader("⭐ Répartition par priorité")
        prio_df = df[df["priorite"] != "A DEFINIR"]
        if not prio_df.empty:
            prio_counts = prio_df.groupby("priorite").size().reset_index(name="count")
            prio_counts = prio_counts.sort_values("priorite")
            
            fig_prio = px.funnel(
                prio_counts,
                x="count", 
                y="priorite",
                color_discrete_sequence=["#6366f1"],
                text="count"
            )
            fig_prio.update_traces(
                textposition="inside",
                textfont_size=14,
                textfont_color="white",
                textfont_family="Inter"
            )
            fig_prio.update_layout(
                margin=dict(t=20),
                font=dict(family="Inter", size=14),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig_prio, use_container_width=True)
        else:
            st.info("Aucune priorité définie pour les demandes validées.")
    
    # Timeline des livraisons
    st.subheader("📅 Timeline des livraisons prévues")
    timeline_df = df[
        (df["statut"].isin(["EN COURS", "NON COMMENCE"])) &
        (df["date_livraison"] != "")
    ].copy()
    
    if not timeline_df.empty:
        # Utiliser date_debut si disponible, sinon date_entree
        timeline_df["timeline_start"] = timeline_df.apply(
            lambda r: r["date_debut"] if r.get("date_debut") and r["date_debut"] else r["date_entree"], axis=1
        )
        timeline_df["timeline_start"] = pd.to_datetime(timeline_df["timeline_start"], errors="coerce")
        timeline_df["date_livraison"] = pd.to_datetime(timeline_df["date_livraison"], errors="coerce")
        timeline_df = timeline_df.dropna(subset=["timeline_start", "date_livraison"])
        
        if not timeline_df.empty:
            fig_tl = px.timeline(
                timeline_df,
                x_start="timeline_start", 
                x_end="date_livraison",
                y="libelle", 
                color="porteur",
                hover_data=["departement", "statut", "priorite"],
            )
            fig_tl.update_yaxes(autorange="reversed")
            fig_tl.update_layout(
                margin=dict(t=20), 
                height=max(350, len(timeline_df)*40+100),
                xaxis_title="Période",
                yaxis_title="",
                font=dict(family="Inter", size=14),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
            )
            st.plotly_chart(fig_tl, use_container_width=True)
        else:
            st.info("Aucune date de livraison planifiée.")
    else:
        st.info("Aucune demande active avec date de livraison.")

# ═════════════════════════════════════════════════════════════════════
# FOOTER MODERNE
# ═════════════════════════════════════════════════════════════════════
st.divider()
st.markdown("""
<div class="footer-text">
    <strong>DATA PRO MAX v2.0</strong> · Application de Pilotage BI · Orange Money<br>
    Développé par le Département Business Intelligence · © 2026
</div>
""", unsafe_allow_html=True)
