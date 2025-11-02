from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import Participant
from django.db.models import Count, Q
from django.shortcuts import render
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
from huggingface_hub import InferenceClient
import os
import pandas as pd
from django.http import HttpResponse
from django.contrib.auth.models import User
from .models import Participant, CustomUser, AdminActionLog  # ← THIS IS CRITICAL
from django.core.paginator import Paginator
from django.db import transaction
from decouple import config

HF_API_KEY = config('HF_API_KEY', default=None)

# For AI report (if used)
try:
    from huggingface_hub import InferenceClient
except ImportError:
    InferenceClient = None

@login_required
def admin_panel(request):
    if not request.user.is_super_admin:
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    
    users = CustomUser.objects.filter(is_staff=True).exclude(id=request.user.id)
    logs = AdminActionLog.objects.select_related('user').order_by('-timestamp')[:20]  # Last 20 actions
    
    return render(request, 'participants/admin_panel.html', {
        'users': users,
        'logs': logs
    })

def log_admin_action(user, action):
    AdminActionLog.objects.create(user=user, action=action)

@login_required
def create_admin_user(request):
    if not request.user.is_super_admin:
        return redirect('dashboard')
    
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        role = request.POST.get('role', 'checkin_admin')
        
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        else:
            user = CustomUser.objects.create_user(
                username=username,
                password=password,
                role=role,
                is_staff=True
            )
            messages.success(request, f"✅ {role.replace('_', ' ').title()} created!")
            return redirect('admin_panel')
    
    return render(request, 'participants/create_admin.html')

@login_required
def delete_participant(request, participant_id):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can delete participants.")
        return redirect('participants_list')
    
    participant = get_object_or_404(Participant, id=participant_id)
    
    if request.method == "POST":
        name = participant.full_name
        participant.delete()
        log_admin_action(request.user, f"DELETED participant: {name}")
        messages.success(request, f"✅ Participant '{name}' deleted.")
    
    return redirect('participants_list')

@login_required
def bulk_delete_participants(request):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can delete participants.")
        return redirect('participants_list')
    
    if request.method == "POST":
        selected_ids = request.POST.getlist('selected_ids')
        if not selected_ids:
            messages.warning(request, "No participants selected for deletion.")
            return redirect('participants_list')
        
        deleted_count = 0
        deleted_names = []
        for pid in selected_ids:
            try:
                p = Participant.objects.get(id=pid)
                deleted_names.append(p.full_name)
                p.delete()
                deleted_count += 1
            except Participant.DoesNotExist:
                continue
        
        if deleted_count > 0:
            log_admin_action(
                request.user,
                f"BULK DELETED {deleted_count} participants: {', '.join(deleted_names[:3])}{'...' if len(deleted_names) > 3 else ''}"
            )
            messages.success(request, f"✅ Deleted {deleted_count} participant(s).")
        else:
            messages.warning(request, "No valid participants were deleted.")
    
    return redirect('participants_list')

@login_required
def delete_all_participants(request):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can delete all participants.")
        return redirect('participants_list')
    
    if request.method == "POST":
        confirmation = request.POST.get('confirmation', '').strip()
        if confirmation == 'DELETE ALL':
            count = Participant.objects.count()
            Participant.objects.all().delete()
            log_admin_action(request.user, f"DELETED ALL {count} PARTICIPANTS")
            messages.success(request, f"✅ All {count} participants have been permanently deleted.")
            return redirect('participants_list')
        else:
            messages.error(request, "❌ Confirmation phrase is incorrect. No data was deleted.")
    
    # At the end of the view (before return):
    return render(request, 'participants/confirm_delete_all.html', {
        'total_count': Participant.objects.count()
    })

@login_required
def add_participant(request):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can add participants.")
        return redirect('participants_list')
    
    if request.method == "POST":
        full_name = request.POST.get('full_name', '').strip()
        nationality = request.POST.get('nationality', '').strip()
        payment_status = request.POST.get('payment_status', 'unpaid')  # 'paid', 'free', 'unpaid'

        if not full_name or not nationality:
            messages.error(request, "Full name and nationality are required.")
            return render(request, 'participants/add_participant.html', {
                'full_name': full_name,
                'nationality': nationality,
                'payment_status': payment_status
            })

        # Set flags based on selection
        if payment_status == 'paid':
            paid, free_access = True, False
        elif payment_status == 'free':
            paid, free_access = False, True
        else:  # unpaid
            paid, free_access = False, False

        participant = Participant.objects.create(
            full_name=full_name,
            nationality=nationality,
            paid=paid,
            free_access=free_access
        )
        log_admin_action(request.user, f"ADDED new participant: {full_name} ({nationality})")
        messages.success(request, f"✅ Participant '{full_name}' added successfully!")
        return redirect('participants_list')
    
    return render(request, 'participants/add_participant.html')

@login_required
def import_real_participants(request):
    if not request.user.is_super_admin:
        messages.error(request, "Only Super Admins can import real data.")
        return redirect('admin_panel')
    
    if request.method == "POST":
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            messages.error(request, "Please upload an Excel file.")
            return render(request, 'participants/import_real.html')
        
        try:
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # Validate columns
            required_cols = ['Full Name', 'Nationality', 'Payment Status']
            if not all(col in df.columns for col in required_cols):
                messages.error(request, f"Missing columns. Required: {', '.join(required_cols)}")
                return render(request, 'participants/import_real.html')
            
            created = 0
            with transaction.atomic():  # Rollback on error
                # In import_real_participants view
                for _, row in df.iterrows():
                    full_name = str(row['Full Name']).strip()
                    nationality = str(row['Nationality']).strip()
                    payment_status = str(row['Payment Status']).strip()
                    
                    if not full_name or not nationality:
                        continue
                                                    
                # ✅ CORRECT MAPPING
                    if payment_status.lower() in ['paid', 'yes', 'true']:
                        paid = True
                        free_access = False
                    elif payment_status.lower() in ['free access', 'free']:
                        paid = False
                        free_access = True
                    else:  # unpaid, no, false, etc.
                        paid = False
                        free_access = False
                    
                    obj, new = Participant.objects.get_or_create(
                        full_name=full_name,
                        nationality=nationality,
                        defaults={'paid': paid, 'free_access': free_access}
                    )
                    if new:
                        created += 1
            
            messages.success(request, f"✅ Successfully imported {created} real participants!")
            return redirect('admin_panel')
            
        except Exception as e:
            messages.error(request, f"❌ Import failed: {str(e)}")
    
    return render(request, 'participants/import_real.html')

@login_required
def ai_report(request):
    # Get stats
    total = Participant.objects.count()
    paid = Participant.objects.filter(paid=True).count()
    present = Participant.objects.filter(is_present=True).count()
    free= Participant.objects.filter(free_access=True).count()  # ← ADD THIS
    inpaid = total - paid - free  # 
    day_time = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    # Build prompt
    prompt = f"""
    You are a professional event coordinator and report writer specialized in scientific and agricultural congresses such as the Arab Congress of Plant Protection (ACPP-ASPP).

    Your task is to generate a **concise, professional, and daily on demand report and summary about what you have as data, not meaning that the event is complete** based on the following real statistics:

    - Total participants: {total}
    - Paid participants: {paid}
    - Confirmed attendance (present): {present}
    - Unpaid participants: {inpaid}
    - Free Access: {free}
    - Current date and time: {day_time}

    - you can check also the website of the event https://acpp-aspp.com/ for more information about the event for each day report.
    Guidelines:
    - Use a clear, objective, and factual tone.
    - Include all three numbers explicitly.
    - Highlight the success and engagement of participants in a positive and encouraging way.
    - The report should be **short, elegant, and easy to read**.
    - Use **a few relevant emojis** to make it visually engaging (like 📊🌿👏 etc.).
    - Write the report in **two versions**:
    1. English version first.
    2. Arabic version second.
    - Keep the structure clean and separated by a line like this:
    -----

    Format output exactly like this:

    [Your English report here] 📊

    -----

    [Your Arabic report here] 📊
    """
    
    try:
        client = InferenceClient(api_key=HF_API_KEY)
        response = client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2-Exp",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8000
        )
        ai_text = response.choices[0].message.content.strip()
    except Exception as e:
        ai_text = "walaa-AI report temporarily unavailable. Event is going well!"

    return JsonResponse({'report': ai_text})

def dashboard(request):
    return render(request, 'participants/dashboard.html')

@login_required
def search_participant(request):
    query = request.GET.get('q', '').strip()
    participants = []
    if query:
        participants = Participant.objects.filter(
            Q(full_name__icontains=query) | Q(nationality__icontains=query)
        )
    return render(request, 'participants/search_results.html', {
        'query': query,
        'participants': participants
    })

def dashboard(request):
    total = Participant.objects.count()
    paid = Participant.objects.filter(paid=True).count()
    free = Participant.objects.filter(free_access=True).count()
    unpaid = Participant.objects.filter(paid=False, free_access=False).count()

    # PRESENCE = is_present=True OR any meal served
    meal_fields = [f'{m}_day{d}' for d in range(1,8) for m in ['breakfast','lunch']]
    q_meals = Q()
    for field in meal_fields:
        q_meals |= Q(**{field: True})
    
    present = Participant.objects.filter(
        Q(is_present=True) | q_meals
    ).count()

    # Meal stats
    meal_data = []
    total_meals = 0
    for day in range(1, 6):  # ← 1 to 5, not 1 to 8
        b = Participant.objects.filter(**{f'breakfast_day{day}': True}).count()
        l = Participant.objects.filter(**{f'lunch_day{day}': True}).count()
        total_day = b + l
        total_meals += total_day
        meal_data.append({
            'day': day,
            'date': ['Nov 3', 'Nov 4', 'Nov 5', 'Nov 6', 'Nov 7'][day - 1],
            'breakfast': b,
            'lunch': l,
            'total': total_day
        })

    chart_data = {
        'paid': paid,
        'unpaid': unpaid,
        'free': free,
        'meal_days': [item['total'] for item in meal_data],
        'meal_labels': [item['date'] for item in meal_data], 
    }

    context = {
        'total': total,
        'paid': paid,
        'free': free,
        'unpaid': unpaid,
        'present': present,
        'total_meals': total_meals,
        'meal_data': meal_data,
        'chart_data': chart_data,
    }
    return render(request, 'participants/dashboard.html', context)
@login_required

def dashboard_stats(request):
    total = Participant.objects.count()
    paid = Participant.objects.filter(paid=True).count()
    free = Participant.objects.filter(free_access=True).count()
    unpaid = total - paid - free  # more accurate

    # ✅ Only consider meals for days 1–5 (Nov 3–7)
    meal_fields = [f'{m}_day{d}' for d in range(1, 6) for m in ['breakfast', 'lunch']]  # days 1 to 5
    q_meals = Q()
    for field in meal_fields:
        q_meals |= Q(**{field: True})
    
    present = Participant.objects.filter(Q(is_present=True) | q_meals).count()

    # ✅ Meal totals for 5 days only
    meal_days = []
    for day in range(1, 6):  # days 1 to 5
        b = Participant.objects.filter(**{f'breakfast_day{day}': True}).count()
        l = Participant.objects.filter(**{f'lunch_day{day}': True}).count()
        meal_days.append(b + l)

    return JsonResponse({
        'total': total,
        'paid': paid,
        'unpaid': unpaid,
        'free': free,  # optional but useful
        'present': present,
        'meal_days': meal_days,  # now length = 5
        'meal_labels': ['Nov 3', 'Nov 4', 'Nov 5', 'Nov 6', 'Nov 7'],  # optional for frontend
    })

@login_required
def checkin_view(request):
    return render(request, 'participants/checkin.html')

@login_required
def scan_qr(request):
    if request.method == "POST":
        qr_data = request.POST.get('qr_data', '').strip()
        
        # Extract name and nationality (ignore payment status in QR)
        parts = qr_data.split('|')
        if len(parts) < 2:
            return render(request, 'participants/error.html', {
                'error': 'Invalid QR format. Expected: Name|Country'
            })
        
        full_name = parts[0].strip()
        nationality = parts[1].strip()

        # Find participant by name + nationality
        try:
            participant = Participant.objects.get(
                full_name=full_name,
                nationality=nationality
            )
            # ✅ ADD scan_success HERE, inside the try block
            return render(request, 'participants/participant_detail.html', {
                'p': participant,
                'from_scan': True  # ← Use 'from_scan' (better name)
            })
        except Participant.DoesNotExist:
            return render(request, 'participants/error.html', {
                'error': f'Participant "{full_name}" from {nationality} not found in system.'
            })
    
    # If not POST, redirect to check-in (should not happen in normal flow)
    return redirect('checkin')

@login_required
def toggle_presence(request, participant_id):
    if request.method != "POST":
        return redirect('dashboard')
    
    p = get_object_or_404(Participant, id=participant_id)
    p.is_present = not p.is_present
    p.save()
    
    status = "confirmed" if p.is_present else "revoked"
    messages.success(request, f"✅ Presence {status}!")
    return redirect('participant_detail', participant_id=participant_id)
@login_required
def toggle_payment(request, participant_id):
    if request.method != "POST":
        return redirect('dashboard')
    
    if not (request.user.is_super_admin or request.user.is_checkin_admin):
        messages.error(request, "You don't have permission to change payment status.")
        return redirect('participant_detail', participant_id=participant_id)
    
    p = get_object_or_404(Participant, id=participant_id)
    
    # Cycle: UNPAID → PAID → FREE → UNPAID
    if not p.paid and not p.free_access:
        # UNPAID → PAID
        p.paid = True
        p.free_access = False
        new_status = "PAID"
    elif p.paid and not p.free_access:
        # PAID → FREE
        p.paid = False
        p.free_access = True
        new_status = "FREE"
    else:
        # FREE → UNPAID
        p.paid = False
        p.free_access = False
        new_status = "UNPAID"
    
    p.save()
    messages.success(request, f"✅ Payment status updated to: {new_status}")
    return redirect('participant_detail', participant_id=participant_id)

@login_required
def toggle_meal(request, participant_id, meal):
    if request.method != "POST":
        return redirect('dashboard')
    
    p = get_object_or_404(Participant, id=participant_id)
    valid_meals = [f'{m}_day{d}' for d in range(1,8) for m in ['breakfast','lunch']]
    
    if meal in valid_meals:
        current = getattr(p, meal)
        setattr(p, meal, not current)
        p.save()
        action = "served" if not current else "revoked"
        messages.success(request, f"✅ Meal '{meal.replace('_', ' ')}' {action}.")
    else:
        messages.error(request, "Invalid meal selection.")
    
    return redirect('participant_detail', participant_id=participant_id)

@login_required
def mark_present(request, participant_id):
    p = get_object_or_404(Participant, id=participant_id)
    if not p.is_present:
        p.is_present = True
        p.save()
        messages.success(request, "✅ Presence confirmed!")
    else:
        messages.info(request, "ℹ️ Already marked as present.")
    return render(request, 'participants/participant_detail.html', {'p': p})

@login_required
def participant_detail_view(request, participant_id):
    p = get_object_or_404(Participant, id=participant_id)
    return render(request, 'participants/participant_detail.html', {'p': p})

@login_required
def export_participants(request):
    participants = Participant.objects.all().values(
        'full_name', 'nationality', 'paid', 'is_present',
        'breakfast_day1', 'lunch_day1',
        'breakfast_day2', 'lunch_day2',
        'breakfast_day3', 'lunch_day3',
        'breakfast_day4', 'lunch_day4',
        'breakfast_day5', 'lunch_day5',
    )
    df = pd.DataFrame(participants)
    df['paid'] = df['paid'].map({True: 'PAID', False: 'UNPAID'})
    df['is_present'] = df['is_present'].map({True: 'YES', False: 'NO'})

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=congress_participants.xlsx'
    df.to_excel(response, index=False)
    return response

@login_required
def edit_admin_role(request, user_id):
    if not request.user.is_super_admin:
        return redirect('dashboard')
    
    user_to_edit = get_object_or_404(CustomUser, id=user_id)
    
    # Prevent editing yourself or other super admins (optional)
    if user_to_edit == request.user:
        messages.error(request, "You cannot edit your own role.")
        return redirect('admin_panel')
    
    if request.method == "POST":
        new_role = request.POST.get('role')
        if new_role in ['super_admin', 'checkin_admin']:
            old_role = user_to_edit.get_role_display()
            user_to_edit.role = new_role
            user_to_edit.save()
            
            log_admin_action(request.user, f"CHANGED ROLE of {user_to_edit.username} from {old_role} to {user_to_edit.get_role_display()}")
            messages.success(request, f"✅ Role updated for {user_to_edit.username}!")
        return redirect('admin_panel')
    
    return render(request, 'participants/edit_role.html', {'user_to_edit': user_to_edit})

@login_required
def delete_admin_user(request, user_id):
    if not request.user.is_super_admin:
        return redirect('dashboard')
    
    user_to_delete = get_object_or_404(CustomUser, id=user_id)
    
    if user_to_delete == request.user:
        messages.error(request, "You cannot delete yourself.")
        return redirect('admin_panel')
    
    if request.method == "POST":
        username = user_to_delete.username
        user_to_delete.delete()
        
        log_admin_action(request.user, f"DELETED USER {username}")
        messages.success(request, f"✅ User {username} deleted!")
        return redirect('admin_panel')
    
    return render(request, 'participants/confirm_delete.html', {'user_to_delete': user_to_delete})

@login_required
def reset_admin_password(request, user_id):
    if not request.user.is_super_admin:
        return redirect('dashboard')
    
    user_to_reset = get_object_or_404(CustomUser, id=user_id)
    
    if user_to_reset == request.user:
        messages.error(request, "You cannot reset your own password here.")
        return redirect('admin_panel')
    
    if request.method == "POST":
        new_password = request.POST.get('password')
        if len(new_password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        else:
            user_to_reset.set_password(new_password)
            user_to_reset.save()
            
            log_admin_action(request.user, f"RESET PASSWORD for {user_to_reset.username}")
            messages.success(request, f"✅ Password reset for {user_to_reset.username}!")
            return redirect('admin_panel')
    
    return render(request, 'participants/reset_password.html', {'user_to_reset': user_to_reset})

@login_required
def participants_list(request):
    query = request.GET.get('q', '').strip()
    participants = Participant.objects.all()
    
    if query:
        participants = participants.filter(
            Q(full_name__icontains=query) | Q(nationality__icontains=query)
        )
    
    participants = participants.order_by('full_name')
    
    # Add pagination (20 participants per page)
    paginator = Paginator(participants, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'participants/participants_list.html', {
        'participants': page_obj,  # ← Pass page_obj instead of full list
        'query': query
    })

@login_required
def edit_participant(request, participant_id):
    p = get_object_or_404(Participant, id=participant_id)
    
    if request.method == "POST":
        p.full_name = request.POST.get('full_name', '').strip()
        p.nationality = request.POST.get('nationality', '').strip()
        p.paid = request.POST.get('paid') == 'on'
        p.save()
        
        # Log the action
        log_admin_action(request.user, f"EDITED participant {p.full_name} ({p.nationality})")
        messages.success(request, "✅ Participant updated successfully!")
        return redirect('participants_list')
    
    return render(request, 'participants/edit_participant.html', {'p': p})