import csv
import os
from botocore.exceptions import ClientError
from config import get_resources

# Configuration
CSV_PATH = "head-admin.csv"  # Ensure this matches your CSV filename
DEFAULT_ROLE = "head-admin"
ALLOWED_DOMAINS = ["WEB", "APP", "AI/ML", "EVENTS", "CC", "PNM", "UI/UX", "VIDEO"]

def seed_admins_from_csv(csv_path):
    resources = get_resources()
    admin_table = resources["admin_table"]

    if not os.path.exists(csv_path):
        print(f"Error: CSV file '{csv_path}' not found.")
        return

    with open(csv_path, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        
        # Check if 'Email' column exists
        if reader.fieldnames and 'email' not in reader.fieldnames:
             print(f"Error: CSV must have an 'email' column. Found: {reader.fieldnames}")
             return

        for row in reader:
            email = row.get("email", "").strip().lower()

            if not email:
                print("Skipping row without email:", row)
                continue

            try:
                # We use put_item to overwrite or create the admin entry
                # This ensures the structure is exactly as requested
                admin_table.put_item(
                    Item={
                        "email": email,
                        "role": DEFAULT_ROLE,
                        "allowed_domains": ALLOWED_DOMAINS
                    }
                )

                print(f"Successfully seeded admin: {email}")

            except ClientError as e:
                print(f"Failed to seed {email}: {e.response['Error']['Message']}")

if __name__ == "__main__":
    seed_admins_from_csv(CSV_PATH)
