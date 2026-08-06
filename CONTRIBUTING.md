# Contribution Guide

Merci de contribuer à ce projet. Voici les règles et le workflow recommandés.

Branches
- `main`: branche stable. Toutes les opérations de création/modification/suppression d'objets doivent être effectuées via l'administration Django. Le dashboard sur `main` est en lecture seule.
- `advanced-features`: branche expérimentale pour prototypage UI et nouvelles fonctionnalités (PWA, commandes IA, etc.). Les contributions nécessitant des écritures depuis le dashboard doivent cibler `advanced-features`.

Workflow
- Fork ou clone le dépôt.
- Créez une branche à partir de `main` ou `advanced-features` selon la nature de la modification.
- Ouvrez une Pull Request vers la branche appropriée, décrivez les changements et ajoutez des tests si nécessaire.

Tests
- Exécutez la suite de tests Django avant de soumettre une PR:

```
stockml\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py test
```

Code review
- Les PR sur `main` requièrent une approbation et des tests passing. Les PR expérimentales peuvent être fusionnées dans `advanced-features` avec plus de flexibilité.

Merci pour votre contribution !
