from flask import Flask, render_template, request, redirect, session
import mysql.connector
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

cursor = conn.cursor()
def role_required(*roles):

    def decorator(f):

        @wraps(f)
        def decorated_function(*args, **kwargs):

            # Vérifier la connexion
            if "id_technicien" not in session:
                return redirect("/login")

            # Vérifier le rôle
            if session.get("role") not in roles:
                return "Accès refusé : vous n'avez pas les permissions nécessaires.", 403

            return f(*args, **kwargs)

        return decorated_function

    return decorator
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        # Chercher l'utilisateur par username
        cursor.execute("""
            SELECT id_technicien, nom, prenom, username, password, role
            FROM technicien
            WHERE username=%s
        """, (username,))

        user = cursor.fetchone()

        # Vérifier le mot de passe
        if user and check_password_hash(user[4], password):

            # Stocker les informations dans la session
            session["id_technicien"] = user[0]
            session["nom"] = user[1]
            session["prenom"] = user[2]
            session["username"] = user[3]
            session["role"] = user[5]

            return redirect("/")

        else:

            return render_template(
                "login.html",
                error="Nom utilisateur ou mot de passe incorrect."
            )

    return render_template("login.html")
@app.route("/logout")
def logout():

    session.clear()

    return redirect("/login")

@app.route("/")
def dashboard():

    # =========================
    # Vérifier connexion
    # =========================

    if "id_technicien" not in session:
        return redirect("/login")


    # =========================
    # Nombre de clients
    # =========================

    cursor.execute("SELECT COUNT(*) FROM client")

    nb_clients = cursor.fetchone()[0]


    # =========================
    # Nombre de machines
    # =========================

    cursor.execute("SELECT COUNT(*) FROM machine")

    nb_machines = cursor.fetchone()[0]


    # =========================
    # Nombre d'interventions
    # =========================

    cursor.execute("SELECT COUNT(*) FROM intervention")

    nb_interventions = cursor.fetchone()[0]


    # =========================
    # Nombre de techniciens
    # =========================

    cursor.execute("SELECT COUNT(*) FROM technicien")

    nb_techniciens = cursor.fetchone()[0]


    # =========================
    # Dernières interventions
    # =========================

    cursor.execute("""
        SELECT
            i.date_intervention,
            CONCAT(c.nom, ' ', c.prenom) AS client,
            CONCAT(m.marque, ' ', m.modele) AS machine,
            i.statut,
            CONCAT(t.prenom, ' ', t.nom) AS technicien

        FROM intervention i

        JOIN machine m
            ON i.id_machine = m.id_machine

        JOIN client c
            ON m.id_client = c.id_client

        JOIN technicien t
            ON i.id_technicien = t.id_technicien

        ORDER BY i.date_intervention DESC

        LIMIT 5
    """)

    dernieres_interventions = cursor.fetchall()


    # =========================
    # 1. Stock faible
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM stock
        WHERE quantite_disponible <= seuil_alerte
    """)

    nb_stock_alertes = cursor.fetchone()[0]


    # =========================
    # 2. Interventions en attente
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM intervention
        WHERE statut = 'En attente'
    """)

    nb_interventions_attente = cursor.fetchone()[0]


    # =========================
    # 3. Interventions en retard
    # =========================

    cursor.execute("""
        SELECT COUNT(*)
        FROM intervention
        WHERE date_intervention < CURDATE()
        AND statut IN ('En attente', 'En cours')
    """)

    nb_interventions_retard = cursor.fetchone()[0]


    # =========================
    # Nombre total notifications
    # =========================

    nb_notifications = (
        nb_stock_alertes
        + nb_interventions_attente
        + nb_interventions_retard
    )


    # =========================
    # Si notifications déjà lues
    # =========================

    if session.get("notifications_lues", False):

        nb_notifications = 0


    # =========================
    # Dashboard
    # =========================

    return render_template(
        "dashboard.html",

        nb_clients=nb_clients,

        nb_machines=nb_machines,

        nb_interventions=nb_interventions,

        nb_techniciens=nb_techniciens,

        dernieres_interventions=dernieres_interventions,

        nb_notifications=nb_notifications
    )    
@app.route("/notifications")
def notifications():

    # =========================
    # Vérifier connexion
    # =========================

    if "id_technicien" not in session:
        return redirect("/login")


    # =========================
    # Marquer les notifications
    # comme lues
    # =========================

    session["notifications_lues"] = True


    # Liste des notifications

    notifications = []


    # =====================================================
    # 1. STOCK FAIBLE
    # =====================================================

    cursor.execute("""
        SELECT
            p.nom,
            s.quantite_disponible,
            s.seuil_alerte

        FROM stock s

        JOIN piecedetachee p
            ON s.id_piece = p.id_piece

        WHERE s.quantite_disponible <= s.seuil_alerte

        ORDER BY s.quantite_disponible ASC
    """)

    stocks_faibles = cursor.fetchall()


    for stock in stocks_faibles:

        notifications.append({

            "type": "stock",

            "titre": "Stock faible",

            "message":
                f"La pièce « {stock[0]} » "
                f"a atteint le seuil d'alerte.",

            "details":
                f"Quantité : {stock[1]} | "
                f"Seuil : {stock[2]}"
        })


    # =====================================================
    # 2. INTERVENTIONS EN ATTENTE
    # =====================================================

    cursor.execute("""
        SELECT
            i.id_intervention,
            i.date_intervention,
            CONCAT(m.marque, ' ', m.modele) AS machine

        FROM intervention i

        JOIN machine m
            ON i.id_machine = m.id_machine

        WHERE i.statut = 'En attente'

        ORDER BY i.date_intervention DESC
    """)

    interventions_attente = cursor.fetchall()


    for intervention in interventions_attente:

        notifications.append({

            "type": "intervention",

            "titre": "Intervention en attente",

            "message":
                f"Une intervention est en attente "
                f"pour la machine "
                f"« {intervention[2]} ».",

            "details":
                f"Date : {intervention[1]}"
        })


    # =====================================================
    # 3. INTERVENTIONS EN RETARD
    # =====================================================

    cursor.execute("""
        SELECT
            i.id_intervention,
            i.date_intervention,
            CONCAT(m.marque, ' ', m.modele) AS machine,
            i.statut

        FROM intervention i

        JOIN machine m
            ON i.id_machine = m.id_machine

        WHERE i.date_intervention < CURDATE()

        AND i.statut IN ('En attente', 'En cours')

        ORDER BY i.date_intervention ASC
    """)

    interventions_retard = cursor.fetchall()


    for intervention in interventions_retard:

        notifications.append({

            "type": "retard",

            "titre": "Intervention en retard",

            "message":
                f"L'intervention de la machine "
                f"« {intervention[2]} » est en retard.",

            "details":
                f"Date prévue : {intervention[1]} | "
                f"Statut : {intervention[3]}"
        })


    # =====================================================
    # Afficher la page notifications
    # =====================================================

    return render_template(
        "notifications.html",

        notifications=notifications
    )
@app.route("/clients")
@role_required("Admin")
def clients():

    cursor.execute("""
        SELECT
            id_client,
            nom,
            prenom,
            adresse,
            telephone,
            email,
            num_fiscal
        FROM client
    """)

    clients = cursor.fetchall()

    return render_template(
        "clients.html",
        clients=clients
    )
@app.route("/add_client", methods=["GET", "POST"])
@role_required("Admin")
def add_client():

    if request.method == "POST":

        nom = request.form["nom"]
        prenom = request.form["prenom"]
        adresse = request.form["adresse"]
        telephone = request.form["telephone"]
        email = request.form["email"]
        num_fiscal = request.form["num_fiscal"]

        cursor.execute("""
            INSERT INTO client
            (
                nom,
                prenom,
                adresse,
                telephone,
                email,
                num_fiscal
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            nom,
            prenom,
            adresse,
            telephone,
            email,
            num_fiscal
        ))

        conn.commit()

        return redirect("/clients")

    return render_template("add_client.html")
@app.route("/edit_client/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_client(id):
    
    if request.method == "POST":

        nom = request.form["nom"]
        prenom = request.form["prenom"]
        adresse = request.form["adresse"]
        telephone = request.form["telephone"]
        email = request.form["email"]
        num_fiscal = request.form["num_fiscal"]

        cursor.execute("""
            UPDATE client
            SET nom=%s,
                prenom=%s,
                adresse=%s,
                telephone=%s,
                email=%s,
                num_fiscal=%s
            WHERE id_client=%s
        """, (
            nom,
            prenom,
            adresse,
            telephone,
            email,
            num_fiscal,
            id
        ))

        conn.commit()

        return redirect("/clients")

    cursor.execute("""
        SELECT
            id_client,
            nom,
            prenom,
            adresse,
            telephone,
            email,
            num_fiscal
        FROM client
        WHERE id_client=%s
    """, (id,))

    client = cursor.fetchone()

    return render_template(
        "edit_client.html",
        client=client
    )
@app.route("/delete_client/<int:id>")
@role_required("Admin")
def delete_client(id):

    # Vérifier si le client possède des machines
    cursor.execute(
        "SELECT COUNT(*) FROM machine WHERE id_client=%s",
        (id,)
    )

    nb_machines = cursor.fetchone()[0]

    # Si le client possède des machines
    if nb_machines > 0:

        return f"""
        <div style="
            font-family: Arial;
            text-align: center;
            margin-top: 100px;
        ">

            <h2 style="color: #dc3545;">
                Impossible de supprimer ce client
            </h2>

            <p>
                Ce client possède encore
                <strong>{nb_machines}</strong>
                machine(s).
            </p>

            <p>
                Supprimez ou réaffectez d'abord les machines
                liées à ce client.
            </p>

            <a href="/clients"
               style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #0d6efd;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
               ">
                Retour aux clients
            </a>

        </div>
        """

    # Si aucune machine n'est liée
    cursor.execute(
        "DELETE FROM client WHERE id_client=%s",
        (id,)
    )

    conn.commit()

    return redirect("/clients")
@app.route("/machines")
def machines():

    # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            m.id_machine,
            m.marque,
            m.modele,
            m.num_serie,
            m.annee_fabrication,
            m.id_client,
            CONCAT(c.nom, ' ', c.prenom) AS client
        FROM machine m
        JOIN client c
            ON m.id_client = c.id_client
        ORDER BY m.id_machine DESC
    """)

    machines = cursor.fetchall()

    return render_template(
        "machines.html",
        machines=machines
    )
@app.route("/add_machine", methods=["GET", "POST"])
@role_required("Admin")
def add_machine():
    
    if request.method == "POST":

        marque = request.form["marque"]
        modele = request.form["modele"]
        num_serie = request.form["num_serie"]
        annee_fabrication = request.form["annee_fabrication"]
        id_client = request.form["id_client"]

        cursor.execute("""
            INSERT INTO machine
            (
                marque,
                modele,
                num_serie,
                annee_fabrication,
                id_client
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            marque,
            modele,
            num_serie,
            annee_fabrication,
            id_client
        ))

        conn.commit()

        return redirect("/machines")

    # Récupérer les clients
    cursor.execute("""
        SELECT
            id_client,
            nom,
            prenom
        FROM client
        ORDER BY nom, prenom
    """)

    clients = cursor.fetchall()

    return render_template(
        "add_machine.html",
        clients=clients
    )
@app.route("/edit_machine/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_machine(id):

    if request.method == "POST":

        marque = request.form["marque"]
        modele = request.form["modele"]
        num_serie = request.form["num_serie"]
        annee_fabrication = request.form["annee_fabrication"]
        id_client = request.form["id_client"]

        cursor.execute("""
            UPDATE machine
            SET marque=%s,
                modele=%s,
                num_serie=%s,
                annee_fabrication=%s,
                id_client=%s
            WHERE id_machine=%s
        """, (
            marque,
            modele,
            num_serie,
            annee_fabrication,
            id_client,
            id
        ))

        conn.commit()

        return redirect("/machines")

    # Récupérer la machine
    cursor.execute("""
        SELECT
            id_machine,
            marque,
            modele,
            num_serie,
            annee_fabrication,
            id_client
        FROM machine
        WHERE id_machine=%s
    """, (id,))

    machine = cursor.fetchone()

    # Récupérer les clients
    cursor.execute("""
        SELECT
            id_client,
            nom,
            prenom
        FROM client
        ORDER BY nom, prenom
    """)

    clients = cursor.fetchall()

    return render_template(
        "edit_machine.html",
        machine=machine,
        clients=clients
    )
@app.route("/delete_machine/<int:id>")
@role_required("Admin")
def delete_machine(id):
    # Vérifier si la machine possède des interventions
    cursor.execute(
        "SELECT COUNT(*) FROM intervention WHERE id_machine=%s",
        (id,)
    )

    nb_interventions = cursor.fetchone()[0]

    # Si la machine possède des interventions
    if nb_interventions > 0:

        return f"""
        <div style="
            font-family: Arial;
            text-align: center;
            margin-top: 100px;
        ">

            <h2 style="color: #dc3545;">
                Impossible de supprimer cette machine
            </h2>

            <p>
                Cette machine possède encore
                <strong>{nb_interventions}</strong>
                intervention(s).
            </p>

            <p>
                Supprimez ou réaffectez d'abord les interventions
                liées à cette machine.
            </p>

            <a href="/machines"
               style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #0d6efd;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
               ">
                Retour aux machines
            </a>

        </div>
        """

    # Supprimer la machine
    cursor.execute(
        "DELETE FROM machine WHERE id_machine=%s",
        (id,)
    )

    conn.commit()

    return redirect("/machines")
@app.route("/techniciens")
@role_required("Admin")
def techniciens():

    cursor.execute("""
        SELECT
            id_technicien,
            nom,
            prenom,
            specialite,
            telephone,
            email
        FROM technicien
    """)

    techniciens = cursor.fetchall()

    return render_template(
        "techniciens.html",
        techniciens=techniciens
    )
@app.route("/add_technicien", methods=["GET", "POST"])
@role_required("Admin")
def add_technicien():
    if request.method == "POST":

        nom = request.form["nom"]
        prenom = request.form["prenom"]
        specialite = request.form["specialite"]
        telephone = request.form["telephone"]
        email = request.form["email"]

        # Générer automatiquement le username
        username = prenom.lower() + "." + nom.lower()

        # Vérifier si le username existe déjà
        cursor.execute(
            "SELECT id_technicien FROM technicien WHERE username=%s",
            (username,)
        )

        existing = cursor.fetchone()

        if existing:

            return render_template(
                "add_technicien.html",
                error="Un compte existe déjà pour ce technicien."
            )

        # Générer un token d'activation
        import secrets

        activation_token = secrets.token_urlsafe(32)

        # Créer le technicien sans mot de passe
        cursor.execute("""
            INSERT INTO technicien
            (
                nom,
                prenom,
                specialite,
                telephone,
                email,
                date_embauche,
                username,
                password,
                role,
                compte_actif,
                activation_token
            )
            VALUES
            (
                %s, %s, %s, %s, %s,
                CURDATE(),
                %s,
                NULL,
                'Technicien',
                FALSE,
                %s
            )
        """, (
            nom,
            prenom,
            specialite,
            telephone,
            email,
            username,
            activation_token
        ))

        conn.commit()

        return redirect("/techniciens")

    return render_template("add_technicien.html")
@app.route("/activate/<token>", methods=["GET", "POST"])
def activate(token):

    # Chercher le compte avec le token
    cursor.execute("""
        SELECT
            id_technicien,
            username,
            compte_actif
        FROM technicien
        WHERE activation_token=%s
    """, (token,))

    user = cursor.fetchone()

    # Token incorrect
    if not user:

        return "Lien d'activation invalide ou expiré."

    id_technicien = user[0]
    username = user[1]
    compte_actif = user[2]

    # Compte déjà activé
    if compte_actif == 1:

        return "Ce compte est déjà activé."

    # Quand le technicien valide le formulaire
    if request.method == "POST":

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Vérifier les deux mots de passe
        if password != confirm_password:

            return render_template(
                "activate.html",
                username=username,
                error="Les mots de passe ne correspondent pas."
            )

        # Hash du mot de passe
        password_hash = generate_password_hash(password)

        # Activer le compte
        cursor.execute("""
            UPDATE technicien
            SET password=%s,
                compte_actif=1,
                activation_token=NULL
            WHERE id_technicien=%s
        """, (
            password_hash,
            id_technicien
        ))

        conn.commit()

        return redirect("/login")

    return render_template(
        "activate.html",
        username=username
    )
@app.route("/edit_technicien/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_technicien(id):

    if request.method == "POST":

        nom = request.form["nom"]
        prenom = request.form["prenom"]
        specialite = request.form["specialite"]
        telephone = request.form["telephone"]
        email = request.form["email"]

        cursor.execute("""
            UPDATE technicien
            SET nom=%s,
                prenom=%s,
                specialite=%s,
                telephone=%s,
                email=%s
            WHERE id_technicien=%s
        """, (
            nom,
            prenom,
            specialite,
            telephone,
            email,
            id
        ))

        conn.commit()

        return redirect("/techniciens")

    cursor.execute("""
        SELECT
            id_technicien,
            nom,
            prenom,
            specialite,
            telephone,
            email
        FROM technicien
        WHERE id_technicien=%s
    """, (id,))

    technicien = cursor.fetchone()

    return render_template(
        "edit_technicien.html",
        technicien=technicien
    )
@app.route("/interventions")
def interventions():

    # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            i.id_intervention,
            i.date_intervention,
            i.duree,
            i.type_intervention,
            i.description,
            CONCAT(m.marque, ' ', m.modele) AS machine,
            CONCAT(t.prenom, ' ', t.nom) AS technicien,
            i.statut
        FROM intervention i

        JOIN machine m
            ON i.id_machine = m.id_machine

        JOIN technicien t
            ON i.id_technicien = t.id_technicien

        ORDER BY i.date_intervention DESC
    """)

    interventions = cursor.fetchall()

    return render_template(
        "interventions.html",
        interventions=interventions
    )
@app.route("/delete_technicien/<int:id>")
@role_required("Admin")
def delete_technicien(id):

    # Vérifier si le technicien possède des interventions
    cursor.execute(
        "SELECT COUNT(*) FROM intervention WHERE id_technicien=%s",
        (id,)
    )

    nb_interventions = cursor.fetchone()[0]

    # Si le technicien possède des interventions
    if nb_interventions > 0:

        return f"""
        <div style="
            font-family: Arial;
            text-align: center;
            margin-top: 100px;
        ">

            <h2 style="color: #dc3545;">
                Impossible de supprimer ce technicien
            </h2>

            <p>
                Ce technicien possède encore
                <strong>{nb_interventions}</strong>
                intervention(s).
            </p>

            <p>
                Supprimez ou réaffectez d'abord les interventions
                liées à ce technicien.
            </p>

            <a href="/techniciens"
               style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #0d6efd;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
               ">
                Retour aux techniciens
            </a>

        </div>
        """

    # Si aucune intervention n'est liée
    cursor.execute(
        "DELETE FROM technicien WHERE id_technicien=%s",
        (id,)
    )

    conn.commit()

    return redirect("/techniciens")
@app.route("/add_intervention", methods=["GET", "POST"])
@role_required("Admin")
def add_intervention():

    # Récupérer les machines

    cursor.execute("""
        SELECT
            id_machine,
            marque,
            modele,
            num_serie
        FROM machine
        ORDER BY marque, modele
    """)

    machines = cursor.fetchall()


    # Récupérer les techniciens

    cursor.execute("""
        SELECT
            id_technicien,
            nom,
            prenom,
            specialite
        FROM technicien
        ORDER BY nom, prenom
    """)

    techniciens = cursor.fetchall()


    if request.method == "POST":

        date_intervention = request.form["date_intervention"]

        duree = request.form.get("duree", "").strip()

        if duree == "":
            duree = None
        else:
            try:
                duree = float(duree.replace(",", "."))
            except ValueError:
                return render_template(
                    "add_intervention.html",
                    machines=machines,
                    techniciens=techniciens,
                    error="La durée doit être un nombre. Exemple : 2.5"
                )
        type_intervention = request.form["type_intervention"]

        description = request.form.get("description")

        id_machine = request.form["id_machine"]

        id_technicien = request.form["id_technicien"]

        statut = request.form["statut"]


        cursor.execute("""
            INSERT INTO intervention
            (
                date_intervention,
                duree,
                type_intervention,
                description,
                id_machine,
                id_technicien,
                statut
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            date_intervention,
            duree,
            type_intervention,
            description,
            id_machine,
            id_technicien,
            statut
        ))


        conn.commit()

        return redirect("/interventions")


    return render_template(
        "add_intervention.html",
        machines=machines,
        techniciens=techniciens
    )
@app.route("/edit_intervention/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_intervention(id):
    # Récupérer les machines
    cursor.execute("""
        SELECT
            id_machine,
            marque,
            modele,
            num_serie
        FROM machine
        ORDER BY marque, modele
    """)

    machines = cursor.fetchall()


    # Récupérer les techniciens
    cursor.execute("""
        SELECT
            id_technicien,
            nom,
            prenom,
            specialite
        FROM technicien
        ORDER BY nom, prenom
    """)

    techniciens = cursor.fetchall()


    # =========================
    # POST : Modifier
    # =========================

    if request.method == "POST":

        date_intervention = request.form["date_intervention"]

        duree = request.form.get("duree", "").strip()

        if duree == "":
            duree = None
        else:
            try:
                duree = float(duree.replace(",", "."))
            except ValueError:

                cursor.execute("""
                    SELECT
                        id_intervention,
                        date_intervention,
                        duree,
                        type_intervention,
                        description,
                        id_machine,
                        id_technicien,
                        statut
                    FROM intervention
                    WHERE id_intervention=%s
                """, (id,))

                intervention = cursor.fetchone()

                return render_template(
                    "edit_intervention.html",
                    intervention=intervention,
                    machines=machines,
                    techniciens=techniciens,
                    error="La durée doit être un nombre. Exemple : 2.5"
                )
        type_intervention = request.form["type_intervention"]

        description = request.form.get("description")

        id_machine = request.form["id_machine"]

        id_technicien = request.form["id_technicien"]

        statut = request.form["statut"]


        # UPDATE

        cursor.execute("""
            UPDATE intervention
            SET
                date_intervention=%s,
                duree=%s,
                type_intervention=%s,
                description=%s,
                id_machine=%s,
                id_technicien=%s,
                statut=%s
            WHERE id_intervention=%s
        """, (
            date_intervention,
            duree,
            type_intervention,
            description,
            id_machine,
            id_technicien,
            statut,
            id
        ))


        conn.commit()

        return redirect("/interventions")


    # =========================
    # GET : Récupérer intervention
    # =========================

    cursor.execute("""
        SELECT
            id_intervention,
            date_intervention,
            duree,
            type_intervention,
            description,
            id_machine,
            id_technicien,
            statut
        FROM intervention
        WHERE id_intervention=%s
    """, (id,))

    intervention = cursor.fetchone()


    return render_template(
        "edit_intervention.html",
        intervention=intervention,
        machines=machines,
        techniciens=techniciens
    )
@app.route("/delete_intervention/<int:id>")
@role_required("Admin")
def delete_intervention(id):
    # Supprimer l'intervention
    cursor.execute(
        "DELETE FROM intervention WHERE id_intervention=%s",
        (id,)
    )

    conn.commit()

    return redirect("/interventions")
@app.route("/stock")
def stock():
     # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")


    cursor.execute("""
        SELECT
            s.id_stock,
            p.nom,
            p.reference,
            s.quantite_disponible,
            s.seuil_alerte,
            s.emplacement,
            s.local,
            s.etagere,
            s.colonne
        FROM stock s
        INNER JOIN piecedetachee p
            ON s.id_piece = p.id_piece
        ORDER BY s.id_stock DESC
    """)

    stocks = cursor.fetchall()

    return render_template(
        "stock.html",
        stocks=stocks
    )
@app.route("/add_stock", methods=["GET", "POST"])
@role_required("Admin")
def add_stock():

    if request.method == "POST":

        id_piece = request.form["id_piece"]
        quantite_disponible = request.form["quantite_disponible"]
        seuil_alerte = request.form["seuil_alerte"]
        emplacement = request.form["emplacement"]
        local = request.form["local"]
        etagere = request.form["etagere"]
        colonne = request.form["colonne"]

        # Vérifier si la pièce existe déjà dans le stock
        cursor.execute(
            "SELECT id_stock FROM stock WHERE id_piece=%s",
            (id_piece,)
        )

        existing = cursor.fetchone()

        if existing:
            return """
            <div style="
                font-family: Arial;
                text-align: center;
                margin-top: 100px;
            ">

                <h2 style="color: #dc3545;">
                    Cette pièce existe déjà dans le stock
                </h2>

                <a href="/stock"
                   style="
                        display: inline-block;
                        margin-top: 20px;
                        padding: 10px 20px;
                        background: #0d6efd;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                   ">
                    Retour au stock
                </a>

            </div>
            """

        cursor.execute("""
            INSERT INTO stock
            (
                id_piece,
                quantite_disponible,
                seuil_alerte,
                emplacement,
                local,
                etagere,
                colonne
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            id_piece,
            quantite_disponible,
            seuil_alerte,
            emplacement,
            local,
            etagere,
            colonne
        ))

        conn.commit()

        return redirect("/stock")


    # Récupérer les pièces détachées
    cursor.execute("""
        SELECT
            id_piece,
            nom,
            reference
        FROM piecedetachee
        ORDER BY nom
    """)

    pieces = cursor.fetchall()

    return render_template(
        "add_stock.html",
        pieces=pieces
    )
@app.route("/edit_stock/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_stock(id):

    if request.method == "POST":

        id_piece = request.form["id_piece"]
        quantite_disponible = request.form["quantite_disponible"]
        seuil_alerte = request.form["seuil_alerte"]
        emplacement = request.form["emplacement"]
        local = request.form["local"]
        etagere = request.form["etagere"]
        colonne = request.form["colonne"]


        cursor.execute("""
            UPDATE stock
            SET
                id_piece=%s,
                quantite_disponible=%s,
                seuil_alerte=%s,
                emplacement=%s,
                local=%s,
                etagere=%s,
                colonne=%s,
                date_modification=NOW()
            WHERE id_stock=%s
        """, (
            id_piece,
            quantite_disponible,
            seuil_alerte,
            emplacement,
            local,
            etagere,
            colonne,
            id
        ))

        conn.commit()

        return redirect("/stock")


    # Récupérer le stock
    cursor.execute("""
        SELECT
            id_stock,
            id_piece,
            quantite_disponible,
            seuil_alerte,
            emplacement,
            local,
            etagere,
            colonne
        FROM stock
        WHERE id_stock=%s
    """, (id,))

    stock = cursor.fetchone()


    # Récupérer les pièces
    cursor.execute("""
        SELECT
            id_piece,
            nom,
            reference
        FROM piecedetachee
        ORDER BY nom
    """)

    pieces = cursor.fetchall()


    return render_template(
        "edit_stock.html",
        stock=stock,
        pieces=pieces
    )
@app.route("/delete_stock/<int:id>")
@role_required("Admin")
def delete_stock(id):

    # Supprimer le stock
    cursor.execute(
        "DELETE FROM stock WHERE id_stock=%s",
        (id,)
    )

    conn.commit()

    return redirect("/stock")
@app.route("/fournisseurs")
def fournisseurs():
    
    # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            id_fournisseur,
            nom,
            adresse,
            telephone,
            email
        FROM fournisseur
        ORDER BY id_fournisseur DESC
    """)

    fournisseurs = cursor.fetchall()

    return render_template(
        "fournisseurs.html",
        fournisseurs=fournisseurs
    )
@app.route("/add_fournisseur", methods=["GET", "POST"])
@role_required("Admin")
def add_fournisseur():

    if request.method == "POST":

        nom = request.form["nom"]
        adresse = request.form["adresse"]
        telephone = request.form["telephone"]
        email = request.form["email"]


        cursor.execute("""
            INSERT INTO fournisseur
            (
                nom,
                adresse,
                telephone,
                email
            )
            VALUES (%s, %s, %s, %s)
        """, (
            nom,
            adresse,
            telephone,
            email
        ))

        conn.commit()

        return redirect("/fournisseurs")


    return render_template("add_fournisseur.html")
@app.route("/edit_fournisseur/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_fournisseur(id):

    if request.method == "POST":

        nom = request.form["nom"]
        adresse = request.form["adresse"]
        telephone = request.form["telephone"]
        email = request.form["email"]


        cursor.execute("""
            UPDATE fournisseur
            SET
                nom=%s,
                adresse=%s,
                telephone=%s,
                email=%s,
                date_modification=NOW()
            WHERE id_fournisseur=%s
        """, (
            nom,
            adresse,
            telephone,
            email,
            id
        ))

        conn.commit()

        return redirect("/fournisseurs")


    cursor.execute("""
        SELECT
            id_fournisseur,
            nom,
            adresse,
            telephone,
            email
        FROM fournisseur
        WHERE id_fournisseur=%s
    """, (id,))

    fournisseur = cursor.fetchone()


    return render_template(
        "edit_fournisseur.html",
        fournisseur=fournisseur
    )
@app.route("/delete_fournisseur/<int:id>")
@role_required("Admin")
def delete_fournisseur(id):
    # Vérifier si le fournisseur possède des pièces
    cursor.execute(
        "SELECT COUNT(*) FROM piecedetachee WHERE id_fournisseur=%s",
        (id,)
    )

    nb_pieces = cursor.fetchone()[0]

    # Si le fournisseur possède encore des pièces
    if nb_pieces > 0:

        return f"""
        <div style="
            font-family: Arial;
            text-align: center;
            margin-top: 100px;
        ">

            <h2 style="color: #dc3545;">
                Impossible de supprimer ce fournisseur
            </h2>

            <p>
                Ce fournisseur possède encore
                <strong>{nb_pieces}</strong>
                pièce(s) détachée(s).
            </p>

            <p>
                Supprimez ou réaffectez d'abord les pièces
                liées à ce fournisseur.
            </p>

            <a href="/fournisseurs"
               style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #0d6efd;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
               ">
                Retour aux fournisseurs
            </a>

        </div>
        """

    # Supprimer le fournisseur
    cursor.execute(
        "DELETE FROM fournisseur WHERE id_fournisseur=%s",
        (id,)
    )

    conn.commit()

    return redirect("/fournisseurs")
@app.route("/pieces")
def pieces():
    # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            p.id_piece,
            p.nom,
            p.reference,
            p.prix_unitaire,
            f.nom,
            p.etat,
            p.prix_vente,
            p.prix_achat
        FROM piecedetachee p
        INNER JOIN fournisseur f
            ON p.id_fournisseur = f.id_fournisseur
        ORDER BY p.id_piece DESC
    """)

    pieces = cursor.fetchall()

    return render_template(
        "pieces.html",
        pieces=pieces
    )
@app.route("/add_piece", methods=["GET", "POST"])
@role_required("Admin")
def add_piece():

    if request.method == "POST":

        nom = request.form["nom"]
        reference = request.form["reference"]
        prix_unitaire = request.form["prix_unitaire"]
        id_fournisseur = request.form["id_fournisseur"]
        etat = request.form["etat"]
        prix_vente = request.form["prix_vente"]
        prix_achat = request.form["prix_achat"]

        cursor.execute("""
            INSERT INTO piecedetachee
            (
                nom,
                reference,
                prix_unitaire,
                id_fournisseur,
                etat,
                prix_vente,
                prix_achat
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            nom,
            reference,
            prix_unitaire,
            id_fournisseur,
            etat,
            prix_vente,
            prix_achat
        ))

        conn.commit()

        return redirect("/pieces")


    cursor.execute("""
        SELECT id_fournisseur, nom
        FROM fournisseur
        ORDER BY nom
    """)

    fournisseurs = cursor.fetchall()

    return render_template(
        "add_piece.html",
        fournisseurs=fournisseurs
    )
@app.route("/edit_piece/<int:id>", methods=["GET", "POST"])
@role_required("Admin")
def edit_piece(id):

    if request.method == "POST":

        nom = request.form["nom"]
        reference = request.form["reference"]
        prix_unitaire = request.form["prix_unitaire"]
        id_fournisseur = request.form["id_fournisseur"]
        etat = request.form["etat"]
        prix_vente = request.form["prix_vente"]
        prix_achat = request.form["prix_achat"]

        cursor.execute("""
            UPDATE piecedetachee
            SET
                nom=%s,
                reference=%s,
                prix_unitaire=%s,
                id_fournisseur=%s,
                etat=%s,
                prix_vente=%s,
                prix_achat=%s,
                date_modification=NOW()
            WHERE id_piece=%s
        """, (
            nom,
            reference,
            prix_unitaire,
            id_fournisseur,
            etat,
            prix_vente,
            prix_achat,
            id
        ))

        conn.commit()

        return redirect("/pieces")


    cursor.execute("""
        SELECT
            id_piece,
            nom,
            reference,
            prix_unitaire,
            id_fournisseur,
            etat,
            prix_vente,
            prix_achat
        FROM piecedetachee
        WHERE id_piece=%s
    """, (id,))

    piece = cursor.fetchone()


    cursor.execute("""
        SELECT id_fournisseur, nom
        FROM fournisseur
        ORDER BY nom
    """)

    fournisseurs = cursor.fetchall()


    return render_template(
        "edit_piece.html",
        piece=piece,
        fournisseurs=fournisseurs
    )
@app.route("/delete_piece/<int:id>")
@role_required("Admin")
def delete_piece(id):

    # Vérifier si la pièce existe dans le stock
    cursor.execute(
        "SELECT COUNT(*) FROM stock WHERE id_piece=%s",
        (id,)
    )

    nb_stock = cursor.fetchone()[0]

    # Si la pièce est encore utilisée dans le stock
    if nb_stock > 0:

        return f"""
        <div style="
            font-family: Arial;
            text-align: center;
            margin-top: 100px;
        ">

            <h2 style="color: #dc3545;">
                Impossible de supprimer cette pièce
            </h2>

            <p>
                Cette pièce est encore utilisée dans le stock.
            </p>

            <p>
                Supprimez d'abord son enregistrement dans le stock.
            </p>

            <a href="/pieces"
               style="
                    display: inline-block;
                    margin-top: 20px;
                    padding: 10px 20px;
                    background: #0d6efd;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
               ">
                Retour aux pièces
            </a>

        </div>
        """

    # Supprimer la pièce
    cursor.execute(
        "DELETE FROM piecedetachee WHERE id_piece=%s",
        (id,)
    )

    conn.commit()

    return redirect("/pieces")
@app.route("/rapports")
@role_required("Admin")
def rapports():

    # =========================
    # STATISTIQUES GENERALES
    # =========================

    cursor.execute("SELECT COUNT(*) FROM client")
    nb_clients = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM machine")
    nb_machines = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM intervention")
    nb_interventions = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM technicien")
    nb_techniciens = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM piecedetachee")
    nb_pieces = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM fournisseur")
    nb_fournisseurs = cursor.fetchone()[0]


    # =========================
    # INTERVENTIONS PAR TYPE
    # =========================

    cursor.execute("""
        SELECT
            type_intervention,
            COUNT(*) AS total
        FROM intervention
        GROUP BY type_intervention
        ORDER BY total DESC
    """)

    interventions_types = cursor.fetchall()


    # =========================
    # DERNIERES INTERVENTIONS
    # =========================

    cursor.execute("""
        SELECT
            i.id_intervention,
            i.date_intervention,
            i.type_intervention,
            i.description,
            CONCAT(m.marque, ' ', m.modele),
            CONCAT(t.nom, ' ', t.prenom)
        FROM intervention i

        INNER JOIN machine m
            ON i.id_machine = m.id_machine

        INNER JOIN technicien t
            ON i.id_technicien = t.id_technicien

        ORDER BY i.date_intervention DESC

        LIMIT 5
    """)

    dernieres_interventions = cursor.fetchall()


    # =========================
    # STOCK
    # =========================

    cursor.execute("""
        SELECT
            COUNT(*)
        FROM stock
        WHERE quantite_disponible > seuil_alerte
    """)

    stock_normal = cursor.fetchone()[0]


    cursor.execute("""
        SELECT
            COUNT(*)
        FROM stock
        WHERE quantite_disponible <= seuil_alerte
        AND quantite_disponible > 0
    """)

    stock_faible = cursor.fetchone()[0]


    cursor.execute("""
        SELECT
            COUNT(*)
        FROM stock
        WHERE quantite_disponible <= 0
    """)

    stock_critique = cursor.fetchone()[0]


    # =========================
    # MACHINES PAR MARQUE
    # =========================

    cursor.execute("""
        SELECT
            marque,
            COUNT(*) AS total
        FROM machine
        GROUP BY marque
        ORDER BY total DESC
    """)

    machines_marques = cursor.fetchall()


    # =========================
    # TECHNICIENS + INTERVENTIONS
    # =========================

    cursor.execute("""
        SELECT
            CONCAT(t.nom, ' ', t.prenom),
            COUNT(i.id_intervention)

        FROM technicien t

        LEFT JOIN intervention i
            ON t.id_technicien = i.id_technicien

        GROUP BY
            t.id_technicien,
            t.nom,
            t.prenom

        ORDER BY COUNT(i.id_intervention) DESC
    """)

    interventions_techniciens = cursor.fetchall()


    # =========================
    # AFFICHER RAPPORTS
    # =========================

    return render_template(
        "rapports.html",

        nb_clients=nb_clients,
        nb_machines=nb_machines,
        nb_interventions=nb_interventions,
        nb_techniciens=nb_techniciens,
        nb_pieces=nb_pieces,
        nb_fournisseurs=nb_fournisseurs,

        interventions_types=interventions_types,
        dernieres_interventions=dernieres_interventions,

        stock_normal=stock_normal,
        stock_faible=stock_faible,
        stock_critique=stock_critique,

        machines_marques=machines_marques,
        interventions_techniciens=interventions_techniciens
    )
@app.route("/calendrier")
def calendrier():
    
    if "id_technicien" not in session:
        return redirect("/login")


    cursor.execute("""
        SELECT
            t.id_tache,
            t.titre,
            t.description,
            t.statut,
            t.priorite,
            t.date_debut,
            t.date_fin,
            CONCAT(te.nom, ' ', te.prenom) AS technicien
        FROM tache t
        INNER JOIN technicien te
            ON t.id_technicien = te.id_technicien
        ORDER BY t.date_debut
    """)

    taches = cursor.fetchall()

    return render_template(
        "calendrier.html",
        taches=taches
    )
@app.route("/parametres")
def parametres():

    if "id_technicien" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            nom,
            telephone,
            email,
            site_web,
            adresse
        FROM entreprise
        WHERE id_entreprise = 1
    """)

    entreprise = cursor.fetchone()

    return render_template(
        "parametres.html",
        entreprise=entreprise
    )
@app.route("/modifier_profil", methods=["POST"])
def modifier_profil():

    if "id_technicien" not in session:
        return redirect("/login")

    nom = request.form["nom"]
    prenom = request.form["prenom"]
    email = request.form["email"]

    cursor.execute("""
        UPDATE technicien
        SET nom = %s,
            prenom = %s,
            email = %s
        WHERE id_technicien = %s
    """, (
        nom,
        prenom,
        email,
        session["id_technicien"]
    ))

    conn.commit()

    session["nom"] = nom
    session["prenom"] = prenom

    return redirect("/parametres")
@app.route("/modifier_entreprise", methods=["POST"])
@role_required("Admin")
def modifier_entreprise():
    
    nom = request.form["nom"]
    telephone = request.form["telephone"]
    email = request.form["email"]
    site_web = request.form["site_web"]
    adresse = request.form["adresse"]

    cursor.execute("""
        UPDATE entreprise
        SET nom = %s,
            telephone = %s,
            email = %s,
            site_web = %s,
            adresse = %s
        WHERE id_entreprise = 1
    """, (
        nom,
        telephone,
        email,
        site_web,
        adresse
    ))

    conn.commit()

    return redirect("/parametres")
@app.route("/modifier_mot_de_passe", methods=["POST"])
def modifier_mot_de_passe():

    # Vérifier que l'utilisateur est connecté
    if "id_technicien" not in session:
        return redirect("/login")

    ancien_password = request.form.get("ancien_password")
    nouveau_password = request.form.get("nouveau_password")
    confirmation_password = request.form.get("confirmation_password")

    # Vérifier que tous les champs sont remplis
    if not ancien_password or not nouveau_password or not confirmation_password:
        return redirect("/parametres?password_error=empty")

    # Vérifier que les deux nouveaux mots de passe sont identiques
    if nouveau_password != confirmation_password:
        return redirect("/parametres?password_error=match")

    # Vérifier la longueur minimale
    if len(nouveau_password) < 8:
        return redirect("/parametres?password_error=length")

    # Récupérer le mot de passe actuel depuis la base
    cursor.execute("""
        SELECT password
        FROM technicien
        WHERE id_technicien = %s
    """, (session["id_technicien"],))

    result = cursor.fetchone()

    if not result:
        return redirect("/parametres?password_error=user")

    password_hash = result[0]

    # Vérifier l'ancien mot de passe
    if not check_password_hash(password_hash, ancien_password):
        return redirect("/parametres?password_error=old")

    # Hasher le nouveau mot de passe
    nouveau_password_hash = generate_password_hash(nouveau_password)

    # Mettre à jour la base de données
    cursor.execute("""
        UPDATE technicien
        SET password = %s,
            date_modification = NOW()
        WHERE id_technicien = %s
    """, (nouveau_password_hash, session["id_technicien"]))

    conn.commit()

    return redirect("/parametres?password_success=1")
if __name__ == "__main__":
    app.run(debug=True)