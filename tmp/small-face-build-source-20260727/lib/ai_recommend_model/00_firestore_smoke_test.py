from google.cloud import firestore

PROJECT_ID = "seolleyeon"

db = firestore.Client(project=PROJECT_ID)

# 아무 컬렉션 하나 읽어보기(없어도 됨)
print("Connected. Listing collections:")
for c in db.collections():
    print("-", c.id)