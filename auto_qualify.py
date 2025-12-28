import boto3
import os
from dotenv import load_dotenv
from decimal import Decimal
from config import initialize

load_dotenv()

# Configuration: Domains to process
DOMAINS = ["WEB", "AI/ML", "CC"]

# Mapping from display names to config.py keys
DOMAIN_KEY_MAP = {
    "WEB": "web",
    "AI/ML": "ai",
    "CC": "cc"
}

# Batch-specific thresholds
BATCH_2024_THRESHOLD = 11  # 2024 batch needs score >= 11
BATCH_2025_THRESHOLD = 6   # 2025 batch needs score >= 6

def auto_qualify(dry_run=True):
    resources = initialize()
    domain_tables = resources['domain_tables']
    user_table = resources['user_table']
    
    from botocore.exceptions import ClientError
    
    print(f"{'='*50}")
    print(f"Running Auto-Qualification Script")
    print(f"Thresholds: 2024 batch >= {BATCH_2024_THRESHOLD}, 2025 batch >= {BATCH_2025_THRESHOLD}")
    print(f"Mode: {'DRY RUN (No changes will be saved)' if dry_run else 'LIVE (Changes WILL be saved)'}")
    print(f"{'='*50}\n")

    for domain in DOMAINS:
        print(f"Processing Domain: {domain}")
        print("-" * 30)
        
        # Get the config key for this domain
        config_key = DOMAIN_KEY_MAP.get(domain, domain.lower())
        table = domain_tables.get(config_key)
        if not table:
            print(f"⚠️ Table for domain {domain} not found, skipping...")
            continue
            
        # Scan the table
        try:
            response = table.scan()
            items = response.get('Items', [])
            
            qualified_count_2024 = 0
            qualified_count_2025 = 0
            already_qualified_count = 0
            
            for user in items:
                email = user.get('email')
                
                # Check if user has a score for round 1
                if 'score1' not in user:
                    continue
                    
                score = user['score1']
                # Handle Decimal type from DynamoDB
                if isinstance(score, Decimal):
                    score = int(score)
                else:
                    try:
                        score = int(score)
                    except (ValueError, TypeError):
                        print(f"⚠️  Skipping {email}: Invalid score format {score}")
                        continue

                # Determine batch and required threshold
                is_2024_batch = '2024' in email
                required_threshold = BATCH_2024_THRESHOLD if is_2024_batch else BATCH_2025_THRESHOLD
                
                # Check if score meets threshold (INCLUSIVE)
                if score >= required_threshold:
                    # Check current status
                    current_status = user.get('qualification_status1')
                    
                    # TEMPORARILY COMMENTED OUT - Force update all users to migrate domain names
                    # if current_status == 'qualified':
                    #     already_qualified_count += 1
                    #     # print(f"  - {email}: Already qualified (Score: {score})") 
                    #     continue
                    
                    if current_status == 'qualified':
                        already_qualified_count += 1
                        
                    batch_label = "2024" if is_2024_batch else "2025"
                    print(f"  ✅ Updating {email} (Score: {score}, Batch: {batch_label})")
                    
                    if is_2024_batch:
                        qualified_count_2024 += 1
                    else:
                        qualified_count_2025 += 1
                    
                    if not dry_run:
                        try:
                            # 1. Update Domain Table
                            table.update_item(
                                Key={'email': email},
                                UpdateExpression="SET qualification_status1 = :s, updated_by = :u",
                                ExpressionAttributeValues={
                                    ':s': 'qualified',
                                    ':u': 'auto_qualify_script'
                                }
                            )
                            
                            # 2. Update Main User Table
                            # We need to update the nested map `status1`
                            # Use ExpressionAttributeNames to handle special characters in domain names (e.g., AI/ML)
                            
                            # First, try to update assuming status1 exists
                            try:
                                user_table.update_item(
                                    Key={'uid': email},
                                    UpdateExpression="SET status1.#domain = :s",
                                    ExpressionAttributeNames={'#domain': domain},
                                    ExpressionAttributeValues={':s': 'qualified'},
                                    ConditionExpression="attribute_exists(status1)"
                                )
                            except ClientError as e:
                                if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                                    # status1 doesn't exist, create it
                                    user_table.update_item(
                                        Key={'uid': email},
                                        UpdateExpression="SET status1 = :m",
                                        ExpressionAttributeValues={
                                            ':m': {domain: 'qualified'}
                                        }
                                    )
                                else:
                                    print(f"    ❌ Error updating user table for {email}: {e}")

                        except Exception as e:
                            print(f"    ❌ Error updating {email}: {e}")
            
            print(f"  -> 2024 Batch Qualified: {qualified_count_2024}")
            print(f"  -> 2025 Batch Qualified: {qualified_count_2025}")
            print(f"  -> Already Qualified: {already_qualified_count}\n")
            
        except Exception as e:
            print(f"❌ Error scanning {domain}: {e}")

    print(f"{'='*50}")
    if dry_run:
        print("Done. This was a DRY RUN. No changes were made.")
        print("To apply changes, run the script and call auto_qualify(dry_run=False)")
    else:
        print("Done. Changes have been applied.")
    print(f"{'='*50}")

if __name__ == "__main__":
    # Default to dry run for safety
    # You can change this to False when ready, or pass it as an argument
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        auto_qualify(dry_run=False)
    else:
        auto_qualify(dry_run=True)
