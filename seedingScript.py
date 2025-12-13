import csv
import os
from botocore.exceptions import ClientError
from config import get_resources   # assuming this file is config.py

CSV_PATH = "usersTesting.csv"   # path to your CSV

def seed_users_from_csv(csv_path):
    resources = get_resources()
    user_table = resources["user_table"]

    with open(csv_path, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            email = row.get("Email", "").strip().lower()
            name = row.get("Name", "").strip()
            reg_no = row.get("Reg. No.", "").strip()

            if not email:
                print("Skipping row without email:", row)
                continue

            try:
                user_table.update_item(
                    Key={
                        "uid": email   # Primary Key is 'uid', not 'email'
                    },
                    UpdateExpression="""
                        SET 
                            #name = :name,
                            reg_no = :reg_no
                    """,
                    ExpressionAttributeNames={
                        "#name": "name"
                    },
                    ExpressionAttributeValues={
                        ":name": name,
                        ":reg_no": reg_no
                    }
                )

                print(f"Seeded / updated safely: {email}")

            except ClientError as e:
                print(f"Failed for {email}: {e.response['Error']['Message']}")

if __name__ == "__main__":
    seed_users_from_csv(CSV_PATH)