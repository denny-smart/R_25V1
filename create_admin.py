import sys
import asyncio
from app.core.supabase import supabase

async def create_admin(email: str):
    print(f"Searching for user with email: {email}")
    
    try:
        # Search for user in profiles table
        # Note: We can't directly query auth.users with the JS client easily for emails 
        # without using the admin api which might be restricted differently,
        # but we can query our public.profiles table which should match auth.users one-to-one.
        
        response = supabase.table('profiles').select('*').eq('email', email).execute()
        
        if not response.data:
            print(f"Error: No user found with email {email}")
            print("Please ensure the user has signed up first.")
            return

        user_profile = response.data[0]
        user_id = user_profile['id']
        current_role = user_profile.get('role', 'user')
        current_approval = user_profile.get('is_approved', False)

        print(f"Found user: {email} (ID: {user_id})")
        print(f"Current Role: {current_role}")
        print(f"Currently Approved: {current_approval}")

        if current_role == 'admin' and current_approval:
            print("User is already an admin and approved.")
            return

        confirm = input(f"Are you sure you want to promote {email} to ADMIN? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled.")
            return

        # Update the user profile
        update_data = {
            'role': 'admin',
            'is_approved': True
        }
        
        update_response = supabase.table('profiles').update(update_data).eq('id', user_id).execute()
        
        if update_response.data:
            print(f"Successfully promoted {email} to ADMIN.")
        else:
            print("Failed to update user profile.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python create_admin.py <user_email>")
        sys.exit(1)
        
    email_arg = sys.argv[1]
    asyncio.run(create_admin(email_arg))
