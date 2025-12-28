import boto3
import os
from dotenv import load_dotenv
from decimal import Decimal
from config import initialize

load_dotenv()

# Domains to process
DOMAINS = ["web", "ai", "cc"]

def unqualify_2024_batch(dry_run=True):
    resources = initialize()
    domain_tables = resources['domain_tables']
    user_table = resources['user_table']
    
    from botocore.exceptions import ClientError
    
    print(f"{'='*50}")
    print(f"Unqualifying 2024 Batch Students")
    print(f"Mode: {'DRY RUN (No changes will be saved)' if dry_run else 'LIVE (Changes WILL be saved)'}")
    print(f"{'='*50}\n")

    for domain in DOMAINS:
        print(f"Processing Domain: {domain.upper()}")
        print("-" * 30)
        
        table = domain_tables.get(domain)
        if not table:
            print(f"⚠️ Table for domain {domain} not found, skipping...")
            continue
            
        # Scan the table for qualified users
        try:
            response = table.scan()
            items = response.get('Items', [])
            
            unqualified_count = 0
            
            for user in items:
                email = user.get('email')
                current_status = user.get('qualification_status1')
                
                # Only process if currently qualified
                if current_status != 'qualified':
                    continue
                
                # Check if email contains "2024" (registration year)
                if '2024' in email:
                    print(f"  ❌ Removing qualification for {email}")
                    unqualified_count += 1
                    
                    if not dry_run:
                        try:
                            # 1. Update Domain Table - REMOVE qualification_status1 attribute
                            table.update_item(
                                Key={'email': email},
                                UpdateExpression="REMOVE qualification_status1 SET updated_by = :u",
                                ExpressionAttributeValues={
                                    ':u': 'unqualify_2024_script'
                                }
                            )
                            
                            # 2. Update Main User Table - REMOVE the domain from status1
                            try:
                                user_table.update_item(
                                    Key={'uid': email},
                                    UpdateExpression=f"REMOVE status1.{domain}"
                                )
                            except ClientError as e:
                                # If status1 or status1.domain doesn't exist, that's fine
                                if e.response['Error']['Code'] != 'ValidationException':
                                    print(f"    ⚠️ Error updating user table for {email}: {e}")

                        except Exception as e:
                            print(f"    ❌ Error updating {email}: {e}")
            
            print(f"  -> Total Unqualified: {unqualified_count}\n")
            
        except Exception as e:
            print(f"❌ Error scanning {domain}: {e}")

    print(f"{'='*50}")
    if dry_run:
        print("Done. This was a DRY RUN. No changes were made.")
        print("To apply changes, run: python3 unqualify_2024_batch.py --live")
    else:
        print("Done. Changes have been applied.")
    print(f"{'='*50}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        unqualify_2024_batch(dry_run=False)
    else:
        unqualify_2024_batch(dry_run=True)
