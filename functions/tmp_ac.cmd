gcloud services list --enabled --project=seolleyeon-final --filter="name:firebaseappcheck" --format="value(name)" & firebase --project seolleyeon-final apps:list 2>nul | more
