import pandas as pd

from sklearn.linear_model import LinearRegression

from .models import Vente


def predire_quantite(produit):

    ventes = Vente.objects.filter(
        produit=produit
    ).order_by("date_vente")

    if ventes.count() < 3:
        return "Pas assez de données"

    data = []

    for index, vente in enumerate(ventes):
        data.append([
            index + 1,
            vente.quantite
        ])

    df = pd.DataFrame(
        data,
        columns=[
            "jour",
            "quantite"
        ]
    )

    X = df[["jour"]]

    y = df["quantite"]

    modele = LinearRegression()

    modele.fit(X, y)

    prochain_jour = [[len(df) + 1]]

    prediction = modele.predict(
        prochain_jour
    )[0]

    return round(
        max(
            prediction,
            0
        ),
        1
    )