import sqlite3
import os
import shutil
import csv
from datetime import datetime
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.list import TwoLineIconListItem, IconLeftWidget, OneLineAvatarIconListItem, ImageLeftWidget, IconRightWidget, MDList, TwoLineAvatarIconListItem
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserIconView
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.core.text import LabelBase
from kivy.properties import StringProperty
from kivy.clock import Clock

# ==========================================
# DATABASE MANAGER
# ==========================================
class DatabaseManager:
    def __init__(self):
        self.db_name = "professional_fund.db"
        self.connect_db()

    def connect_db(self):
        self.conn = sqlite3.connect(self.db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()

    def setup_database(self):
        # Base Tables
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS members (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)''')
        try: 
            self.cursor.execute("ALTER TABLE members ADD COLUMN image TEXT DEFAULT ''")
        except Exception: 
            pass 

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS funds (id INTEGER PRIMARY KEY AUTOINCREMENT, member_id INTEGER, month TEXT, week TEXT, date TEXT, amount INTEGER, type TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(member_id) REFERENCES members(id))''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS default_amounts (id INTEGER PRIMARY KEY AUTOINCREMENT, amount INTEGER UNIQUE)''')
        
        # Expenses Table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT, amount INTEGER, date TEXT, month TEXT, category TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        # Backward compatibility for old users
        try: 
            self.cursor.execute("ALTER TABLE expenses ADD COLUMN month TEXT DEFAULT ''")
        except Exception: 
            pass 
        try: 
            self.cursor.execute("ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'General'")
        except Exception: 
            pass 

        # App Settings Config Table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS app_config (setting_key TEXT UNIQUE, setting_value TEXT)''')
        
        # Insert Default Settings if not exists
        default_settings = [
            ('app_title', 'S O H A I B   S A L E E M'),
            ('currency', 'PKR'),
            ('app_pin', ''),
            ('budget_limit', '0'),
            ('auto_backup', '0')
        ]
        for key, val in default_settings:
            try: 
                self.cursor.execute("INSERT INTO app_config (setting_key, setting_value) VALUES (?, ?)", (key, val))
            except sqlite3.IntegrityError: 
                pass
            
        self.conn.commit()
        
        self.cursor.execute("SELECT COUNT(*) FROM default_amounts")
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute("INSERT INTO default_amounts (amount) VALUES (20)")
            self.conn.commit()

    # --- Config Methods ---
    def get_config(self, key):
        self.cursor.execute("SELECT setting_value FROM app_config WHERE setting_key = ?", (key,))
        res = self.cursor.fetchone()
        return res[0] if res else ""

    def update_config(self, key, value):
        self.cursor.execute("UPDATE app_config SET setting_value = ? WHERE setting_key = ?", (str(value), key))
        self.conn.commit()

    # --- Members ---
    def add_member(self, name, image_path=""):
        try:
            self.cursor.execute("INSERT INTO members (name, image) VALUES (?, ?)", (name, image_path))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_member(self, member_id):
        self.cursor.execute("DELETE FROM funds WHERE member_id = ?", (member_id,))
        self.cursor.execute("DELETE FROM members WHERE id = ?", (member_id,))
        self.conn.commit()

    def get_all_members(self):
        self.cursor.execute("SELECT id, name, image FROM members")
        return self.cursor.fetchall()

    def get_member_total_fund(self, member_id):
        self.cursor.execute("SELECT SUM(amount) FROM funds WHERE member_id = ?", (member_id,))
        return self.cursor.fetchone()[0] or 0

    def get_pending_members(self, month):
        self.cursor.execute("SELECT name, image FROM members WHERE id NOT IN (SELECT member_id FROM funds WHERE month = ?)", (month,))
        return self.cursor.fetchall()

    # --- Funds & Expenses ---
    def add_fund(self, member_id, month, week, date, amount, fund_type):
        self.cursor.execute("INSERT INTO funds (member_id, month, week, date, amount, type) VALUES (?, ?, ?, ?, ?, ?)", (member_id, month, week, date, int(amount), fund_type))
        self.conn.commit()

    def add_expense(self, description, amount, date, month, category):
        self.cursor.execute("INSERT INTO expenses (description, amount, date, month, category) VALUES (?, ?, ?, ?, ?)", (description, int(amount), date, month, category))
        self.conn.commit()

    def delete_fund(self, f_id):
        self.cursor.execute("DELETE FROM funds WHERE id = ?", (f_id,))
        self.conn.commit()

    def delete_expense(self, e_id):
        self.cursor.execute("DELETE FROM expenses WHERE id = ?", (e_id,))
        self.conn.commit()

    # --- Stats & Filters ---
    def get_unique_months(self):
        self.cursor.execute("SELECT DISTINCT month FROM funds UNION SELECT DISTINCT month FROM expenses")
        months = [row[0] for row in self.cursor.fetchall() if row[0]]
        return sorted(months)

    def get_dashboard_stats(self, month=None):
        if month:
            self.cursor.execute("SELECT SUM(amount) FROM funds WHERE month=?", (month,))
            total_fund = self.cursor.fetchone()[0] or 0
            self.cursor.execute("SELECT SUM(amount) FROM expenses WHERE month=?", (month,))
            total_expense = self.cursor.fetchone()[0] or 0
            self.cursor.execute("SELECT SUM(amount) FROM funds WHERE type='Extra' AND month=?", (month,))
            total_extra = self.cursor.fetchone()[0] or 0
        else:
            self.cursor.execute("SELECT SUM(amount) FROM funds")
            total_fund = self.cursor.fetchone()[0] or 0
            self.cursor.execute("SELECT SUM(amount) FROM expenses")
            total_expense = self.cursor.fetchone()[0] or 0
            self.cursor.execute("SELECT SUM(amount) FROM funds WHERE type='Extra'")
            total_extra = self.cursor.fetchone()[0] or 0
            
        total_income = total_fund - total_expense
        self.cursor.execute("SELECT COUNT(*) FROM members")
        total_members = self.cursor.fetchone()[0] or 0
        
        return total_income, total_expense, total_extra, total_members

    def search_history(self, search_text, month=None, member_filter=None, sort_order="Newest First"):
        query = "SELECT funds.id, members.name, funds.amount, funds.date, funds.week, funds.type FROM funds JOIN members ON funds.member_id = members.id"
        params = []
        conditions = []
        
        if month:
            conditions.append("funds.month = ?")
            params.append(month)
        if member_filter and member_filter != "All Members":
            conditions.append("members.name = ?")
            params.append(member_filter)
        if search_text:
            conditions.append("(members.name LIKE ? OR funds.amount LIKE ? OR funds.week LIKE ?)")
            params.extend([f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"])
            
        if conditions: query += " WHERE " + " AND ".join(conditions)
            
        if sort_order == "Newest First": query += " ORDER BY funds.id DESC"
        elif sort_order == "Oldest First": query += " ORDER BY funds.id ASC"
        elif sort_order == "Highest Amount": query += " ORDER BY funds.amount DESC"
        
        self.cursor.execute(query, tuple(params))
        return self.cursor.fetchall()

    def get_all_expenses(self, month=None):
        if month: 
            self.cursor.execute("SELECT id, description, amount, date, category FROM expenses WHERE month=? ORDER BY id DESC", (month,))
        else: 
            self.cursor.execute("SELECT id, description, amount, date, category FROM expenses ORDER BY id DESC")
        return self.cursor.fetchall()

    def get_default_amounts(self):
        self.cursor.execute("SELECT id, amount FROM default_amounts ORDER BY amount ASC")
        return self.cursor.fetchall()
        
    def add_default_amount(self, amount):
        try:
            self.cursor.execute("INSERT INTO default_amounts (amount) VALUES (?)", (int(amount),))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError: 
            return False

    def delete_default_amount(self, a_id):
        self.cursor.execute("DELETE FROM default_amounts WHERE id = ?", (a_id,))
        self.conn.commit()

    def reset_all_data(self):
        self.cursor.execute("DELETE FROM funds")
        self.cursor.execute("DELETE FROM expenses")
        self.cursor.execute("DELETE FROM members")
        self.cursor.execute("DELETE FROM sqlite_sequence")
        self.conn.commit()

# ==========================================
# MODERN UI DESIGN (KV STRING)
# ==========================================
KV = """
<WeekListItem@OneLineAvatarIconListItem>:
    text: ""
    CheckboxLeftWidget:
        id: chk
        on_active: app.on_week_check(self.active, root.text)

<DeletableHistoryItem@TwoLineAvatarIconListItem>:
    record_id: 0
    record_type: ""
    icon_left: "cash"
    icon_color: 1, 1, 1, 1
    IconLeftWidget:
        icon: root.icon_left
        theme_text_color: "Custom"
        text_color: root.icon_color
    IconRightWidget:
        icon: "trash-can"
        theme_text_color: "Custom"
        text_color: 1, 0, 0, 1
        on_release: app.confirm_delete_record(root.record_id, root.record_type)

<MemberListItem@TwoLineAvatarIconListItem>:
    member_id: 0
    member_name: ""
    icon_left: "account"
    image_src: ""
    ImageLeftWidget:
        source: root.image_src if root.image_src else ""
        opacity: 1 if root.image_src else 0
    IconLeftWidget:
        icon: root.icon_left
        opacity: 0 if root.image_src else 1
    IconRightWidget:
        icon: "trash-can"
        theme_text_color: "Custom"
        text_color: 1, 0, 0, 1
        on_release: app.confirm_delete_member(root.member_id, root.member_name)

MDScreen:
    MDBoxLayout:
        orientation: 'vertical'
        
        MDTopAppBar:
            title: app.app_title
            elevation: 4
            md_bg_color: app.theme_cls.primary_color
            specific_text_color: 1, 1, 1, 1
            
        MDBoxLayout:
            size_hint_y: None
            height: "55dp"
            md_bg_color: app.theme_cls.bg_dark
            padding: "10dp"
            spacing: "5dp"
            MDLabel:
                text: "Filter:"
                size_hint_x: 0.2
                theme_text_color: "Hint"
            MDLabel:
                id: lbl_current_month_filter
                text: "All Months"
                theme_text_color: "Primary"
                bold: True
            MDIconButton:
                id: btn_month_filter
                icon: "calendar-month"
                theme_text_color: "Custom"
                text_color: app.theme_cls.primary_color
                on_release: app.month_filter_menu.open()
            MDRaisedButton:
                text: "Pending Dues"
                md_bg_color: 1, 0.5, 0, 1
                size_hint_y: None
                height: "35dp"
                on_release: app.show_pending_dues()

        MDBottomNavigation:
            id: bottom_nav
            panel_color: app.theme_cls.bg_dark
            
            # ================= 1. DASHBOARD =================
            MDBottomNavigationItem:
                name: 'screen_dash'
                text: 'Dashboard'
                icon: 'view-dashboard'
                
                MDScrollView:
                    MDBoxLayout:
                        orientation: 'vertical'
                        padding: "20dp"
                        spacing: "20dp"
                        adaptive_height: True
                        
                        MDCard:
                            size_hint_y: None
                            height: "120dp"
                            padding: "15dp"
                            elevation: 3
                            radius: [15, 15, 15, 15]
                            md_bg_color: 0.1, 0.5, 0.8, 1
                            MDBoxLayout:
                                orientation: 'vertical'
                                MDLabel:
                                    text: "Grand Total Income (After Expenses)"
                                    theme_text_color: "Custom"
                                    text_color: 1, 1, 1, 0.8
                                    font_style: "H6"
                                MDLabel:
                                    id: lbl_total_income
                                    text: f"0 {app.currency}"
                                    theme_text_color: "Custom"
                                    text_color: 1, 1, 1, 1
                                    font_style: "H3"
                                    bold: True
                        
                        MDLabel:
                            id: lbl_budget_warning
                            text: "⚠️ Warning: Monthly Budget Exceeded!"
                            theme_text_color: "Error"
                            bold: True
                            opacity: 0
                            size_hint_y: None
                            height: "0dp"
                            
                        MDGridLayout:
                            cols: 2
                            spacing: "15dp"
                            adaptive_height: True
                            
                            MDCard:
                                size_hint_y: None
                                height: "90dp"
                                padding: "15dp"
                                orientation: "vertical"
                                elevation: 2
                                radius: [10, 10, 10, 10]
                                MDLabel:
                                    text: "Total Expenses"
                                    font_style: "Caption"
                                MDLabel:
                                    id: lbl_total_expense
                                    text: f"0 {app.currency}"
                                    font_style: "H5"
                                    theme_text_color: "Error"
                                    
                            MDCard:
                                size_hint_y: None
                                height: "90dp"
                                padding: "15dp"
                                orientation: "vertical"
                                elevation: 2
                                radius: [10, 10, 10, 10]
                                ripple_behavior: True
                                on_release: app.show_total_members_popup()
                                MDLabel:
                                    text: "Total Members"
                                    font_style: "Caption"
                                MDLabel:
                                    id: lbl_total_members
                                    text: "0"
                                    font_style: "H5"
                                    theme_text_color: "Primary"
                                    
                            MDCard:
                                size_hint_y: None
                                height: "90dp"
                                padding: "15dp"
                                orientation: "vertical"
                                elevation: 2
                                radius: [10, 10, 10, 10]
                                MDLabel:
                                    text: "Extra Fund"
                                    font_style: "Caption"
                                MDLabel:
                                    id: lbl_total_extra
                                    text: f"0 {app.currency}"
                                    font_style: "H5"
                                    theme_text_color: "Custom"
                                    text_color: 0, 0.8, 0.4, 1

            # ================= 2. ADD FUND =================
            MDBottomNavigationItem:
                name: 'screen_add'
                text: 'Add Fund'
                icon: 'cash-plus'
                
                MDScrollView:
                    MDBoxLayout:
                        orientation: 'vertical'
                        padding: "20dp"
                        spacing: "20dp"
                        adaptive_height: True
                        
                        MDLabel:
                            text: "New Fund Entry"
                            font_style: "H5"
                            size_hint_y: None
                            height: self.texture_size[1]
                            
                        MDTextField:
                            id: input_member
                            hint_text: "Select Member"
                            icon_right: "account-arrow-down"
                            readonly: True
                            on_focus: if self.focus: app.member_menu.open()
                            
                        MDTextField:
                            id: input_week
                            hint_text: "Select Week(s) & Advance"
                            icon_right: "calendar-multiselect"
                            readonly: True
                            on_focus: if self.focus: app.open_week_dialog()
                            
                        MDBoxLayout:
                            orientation: 'horizontal'
                            spacing: "10dp"
                            size_hint_y: None
                            height: "60dp"
                            
                            MDTextField:
                                id: input_day
                                hint_text: "Day"
                                readonly: True
                                on_focus: if self.focus: app.day_menu.open()
                            
                            MDTextField:
                                id: input_month
                                hint_text: "Month"
                                readonly: True
                                on_focus: if self.focus: app.month_menu.open()
                                
                            MDTextField:
                                id: input_year
                                hint_text: "Year"
                                readonly: True
                                on_focus: if self.focus: app.year_menu.open()
                                
                        MDTextField:
                            id: input_amount
                            hint_text: f"Amount per Week ({app.currency})"
                            icon_right: "menu-down"
                            readonly: True
                            on_focus: if self.focus: app.amount_menu.open()
                            
                        MDRaisedButton:
                            text: "SAVE RECORD"
                            md_bg_color: app.theme_cls.primary_color
                            pos_hint: {"center_x": .5}
                            elevation: 2
                            on_release: app.save_new_fund()

            # ================= 3. KARCH (EXPENSES) =================
            MDBottomNavigationItem:
                name: 'screen_expenses'
                text: 'Karch'
                icon: 'cart-minus'
                on_tab_press: app.load_expenses()
                
                MDBoxLayout:
                    orientation: 'vertical'
                    MDBoxLayout:
                        orientation: 'vertical'
                        padding: "20dp"
                        spacing: "15dp"
                        size_hint_y: None
                        height: "280dp"
                        
                        MDTextField:
                            id: input_expense_category
                            hint_text: "Select Category"
                            icon_right: "menu-down"
                            readonly: True
                            on_focus: if self.focus: app.category_menu.open()
                            
                        MDTextField:
                            id: input_expense_desc
                            hint_text: "Kya liya hai? (Description)"
                            icon_right: "shopping"
                            
                        MDTextField:
                            id: input_expense_amount
                            hint_text: f"Kitne paise lagay? ({app.currency})"
                            input_filter: "int"
                            icon_right: "cash-minus"
                            
                        MDRaisedButton:
                            text: "SAVE EXPENSE"
                            md_bg_color: 1, 0.2, 0.2, 1
                            pos_hint: {"center_x": .5}
                            on_release: app.save_expense()
                            
                    MDLabel:
                        text: "  Expense History"
                        font_style: "Subtitle1"
                        size_hint_y: None
                        height: "30dp"
                        theme_text_color: "Hint"
                        
                    MDScrollView:
                        MDList:
                            id: expenses_list

            # ================= 4. HISTORY =================
            MDBottomNavigationItem:
                name: 'screen_history'
                text: 'History'
                icon: 'history'
                on_tab_press: app.load_history()
                
                MDBoxLayout:
                    orientation: 'vertical'
                    
                    MDBoxLayout:
                        size_hint_y: None
                        height: "70dp"
                        padding: "10dp"
                        spacing: "5dp"
                        MDIconButton:
                            id: btn_member_filter
                            icon: "filter-variant"
                            on_release: app.member_filter_menu.open()
                        MDTextField:
                            id: search_field
                            hint_text: "Search Name / Amount..."
                            on_text: app.load_history(self.text)
                        MDIconButton:
                            id: btn_sort
                            icon: "sort-clock-descending"
                            on_release: app.sort_menu.open()
                            
                    MDScrollView:
                        MDList:
                            id: history_list

            # ================= 5. MEMBERS =================
            MDBottomNavigationItem:
                name: 'screen_members'
                text: 'Members'
                icon: 'account-group'
                on_tab_press: app.load_manage_members()
                
                MDBoxLayout:
                    orientation: 'vertical'
                    spacing: "10dp"
                    
                    MDCard:
                        size_hint_y: None
                        height: "220dp"
                        padding: "15dp"
                        orientation: "vertical"
                        spacing: "10dp"
                        elevation: 1
                        
                        MDLabel:
                            text: "Add New Member"
                            font_style: "H6"
                            size_hint_y: None
                            height: "30dp"
                            
                        MDBoxLayout:
                            spacing: "15dp"
                            size_hint_y: None
                            height: "60dp"
                            
                            FitImage:
                                id: img_preview
                                source: "https://cdn-icons-png.flaticon.com/512/149/149071.png" 
                                size_hint: None, None
                                size: "60dp", "60dp"
                                radius: [30, 30, 30, 30]
                                
                            MDFlatButton:
                                text: "Select Picture"
                                theme_text_color: "Custom"
                                text_color: app.theme_cls.primary_color
                                pos_hint: {"center_y": .5}
                                on_release: app.open_file_chooser("member")
                                
                        MDTextField:
                            id: input_new_member
                            hint_text: "Enter Member Name"
                            icon_right: "account-plus"
                            
                        MDRaisedButton:
                            text: "ADD NEW MEMBER"
                            on_release: app.add_new_member()
                            pos_hint: {"center_x": .5}
                            
                    MDBoxLayout:
                        padding: "10dp"
                        MDLabel:
                            text: "Manage Existing Members & Stats"
                            font_style: "Subtitle1"
                            theme_text_color: "Hint"
                            
                    MDScrollView:
                        MDList:
                            id: manage_members_list

            # ================= 6. SETTINGS =================
            MDBottomNavigationItem:
                name: 'screen_settings'
                text: 'Settings'
                icon: 'cog'
                on_tab_press: app.load_settings()
                
                MDScrollView:
                    MDBoxLayout:
                        orientation: 'vertical'
                        padding: "20dp"
                        spacing: "20dp"
                        adaptive_height: True
                        
                        MDLabel:
                            text: "App Preferences & Security"
                            font_style: "H5"
                            size_hint_y: None
                            height: "30dp"
                            
                        MDTextField:
                            id: set_app_title
                            hint_text: "App Title (e.g. Room Fund)"
                        MDTextField:
                            id: set_currency
                            hint_text: "Currency Symbol (e.g. PKR, $)"
                        MDTextField:
                            id: set_budget
                            hint_text: "Monthly Budget Limit (0 = Disable)"
                            input_filter: "int"
                        MDTextField:
                            id: set_pin
                            hint_text: "App Lock PIN (Leave blank to disable)"
                            password: True
                            input_filter: "int"
                            max_text_length: 4
                            
                        MDBoxLayout:
                            size_hint_y: None
                            height: "40dp"
                            MDLabel:
                                text: "Auto-Backup on Save"
                            MDSwitch:
                                id: sw_auto_backup
                        
                        MDRaisedButton:
                            text: "SAVE SETTINGS"
                            md_bg_color: app.theme_cls.primary_color
                            size_hint_x: 1
                            on_release: app.save_app_settings()

                        MDBoxLayout:
                            size_hint_y: None
                            height: "40dp"
                            MDLabel:
                                text: "Dark Mode"
                            MDSwitch:
                                active: True if app.theme_cls.theme_style == "Dark" else False
                                on_active: app.toggle_theme(self.active)
                                
                        MDRaisedButton:
                            text: "Change App Font (.ttf)"
                            icon: "format-font"
                            md_bg_color: 0.2, 0.5, 0.8, 1
                            size_hint_x: 1
                            on_release: app.open_file_chooser("font")
                            
                        MDRaisedButton:
                            text: "Export Report to CSV/Excel"
                            icon: "file-excel"
                            md_bg_color: 0.1, 0.6, 0.2, 1
                            size_hint_x: 1
                            on_release: app.export_to_csv()
                            
                        MDBoxLayout:
                            spacing: "10dp"
                            size_hint_y: None
                            height: "40dp"
                            MDRaisedButton:
                                text: "Backup DB"
                                size_hint_x: 0.5
                                on_release: app.backup_db(False)
                            MDRaisedButton:
                                text: "Restore DB"
                                size_hint_x: 0.5
                                on_release: app.open_file_chooser("restore")
                                
                        MDBoxLayout:
                            spacing: "10dp"
                            size_hint_y: None
                            height: "40dp"
                            MDRaisedButton:
                                text: "Clear Image Cache"
                                size_hint_x: 0.5
                                md_bg_color: 1, 0.5, 0, 1
                                on_release: app.clear_image_cache()
                            MDRaisedButton:
                                text: "FACTORY RESET"
                                md_bg_color: 1, 0, 0, 1
                                size_hint_x: 0.5
                                on_release: app.confirm_factory_reset()

                        MDLabel:
                            text: "Manage Default Amounts"
                            font_style: "H6"
                            size_hint_y: None
                            height: "30dp"
                            
                        MDBoxLayout:
                            size_hint_y: None
                            height: "60dp"
                            spacing: "10dp"
                            MDTextField:
                                id: input_new_amount
                                hint_text: "Enter New Amount"
                                input_filter: "int"
                            MDRaisedButton:
                                text: "ADD"
                                md_bg_color: app.theme_cls.primary_color
                                pos_hint: {"center_y": .5}
                                on_release: app.add_setting_amount()
                                
                        MDList:
                            id: settings_amount_list
"""

# ==========================================
# APPLICATION LOGIC
# ==========================================
class RoomFundApp(MDApp):
    dialog = None
    week_dialog = None
    
    month_filter_menu = None
    member_filter_menu = None
    sort_menu = None
    
    selected_image_path = "" 
    selected_weeks = []
    current_filter_month = None
    current_member_filter = "All Members"
    current_sort_order = "Newest First"

    app_title = StringProperty("S O H A I B   S A L E E M")
    currency = StringProperty("PKR")

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.accent_palette = "Cyan"
        
        if not os.path.exists("app_images"): os.makedirs("app_images")
        if not os.path.exists("app_fonts"): os.makedirs("app_fonts")
        
        self.custom_font_path = "app_fonts/custom.ttf"
            
        self.db = DatabaseManager()
        self.root = Builder.load_string(KV)
        
        self.load_app_configs_to_vars()
        return self.root

    def on_start(self):
        self.apply_custom_font_if_exists()
        self.check_pin_lock()
        
        now = datetime.now()
        self.root.ids.input_day.text = now.strftime("%d")
        self.root.ids.input_month.text = now.strftime("%b")
        self.root.ids.input_year.text = now.strftime("%Y")
        
        self.current_filter_month = f"{now.strftime('%b')} {now.strftime('%Y')}"
        self.root.ids.lbl_current_month_filter.text = self.current_filter_month
        
        self.setup_menus()
        self.update_all_views()

    # ====== App Lock (PIN Security) ======
    def check_pin_lock(self):
        saved_pin = self.db.get_config('app_pin')
        if saved_pin:
            content = MDBoxLayout(orientation='vertical', size_hint_y=None, height="100dp", padding="10dp")
            self.pin_input = Factory.MDTextField(hint_text="Enter PIN to Unlock", password=True, input_filter="int", halign="center")
            content.add_widget(self.pin_input)
            
            self.pin_dialog = MDDialog(
                title="App Locked 🔒",
                type="custom",
                content_cls=content,
                auto_dismiss=False,
                buttons=[MDRaisedButton(text="UNLOCK", on_release=lambda x: self.verify_pin(saved_pin))]
            )
            self.pin_dialog.open()

    def verify_pin(self, correct_pin):
        if self.pin_input.text == correct_pin: self.pin_dialog.dismiss()
        else: self.pin_input.error = True

    # ====== Dynamic Configs ======
    def load_app_configs_to_vars(self):
        self.app_title = self.db.get_config('app_title') or "Room Fund"
        self.currency = self.db.get_config('currency') or "PKR"

    def save_app_settings(self):
        self.db.update_config('app_title', self.root.ids.set_app_title.text)
        self.db.update_config('currency', self.root.ids.set_currency.text)
        self.db.update_config('budget_limit', self.root.ids.set_budget.text)
        self.db.update_config('app_pin', self.root.ids.set_pin.text)
        self.db.update_config('auto_backup', "1" if self.root.ids.sw_auto_backup.active else "0")
        
        self.load_app_configs_to_vars()
        self.update_dashboard() 
        self.show_dialog("Success", "Settings Saved Successfully!")

    def load_settings(self):
        self.root.ids.set_app_title.text = self.app_title
        self.root.ids.set_currency.text = self.currency
        self.root.ids.set_budget.text = self.db.get_config('budget_limit')
        self.root.ids.set_pin.text = self.db.get_config('app_pin')
        self.root.ids.sw_auto_backup.active = True if self.db.get_config('auto_backup') == "1" else False
        
        lst = self.root.ids.settings_amount_list
        lst.clear_widgets()
        for a_id, amt in self.db.get_default_amounts():
            item = OneLineAvatarIconListItem(text=f"{amt} {self.currency}")
            item.add_widget(IconRightWidget(icon="trash-can", text_color=(1,0,0,1), theme_text_color="Custom", on_release=lambda x, a_id=a_id: self.delete_setting_amount(a_id)))
            lst.add_widget(item)

    def apply_custom_font_if_exists(self):
        if os.path.exists(self.custom_font_path):
            try:
                LabelBase.register(name="CustomAppFont", fn_regular=self.custom_font_path)
                for style in self.theme_cls.font_styles.keys():
                    if isinstance(self.theme_cls.font_styles[style], list):
                        self.theme_cls.font_styles[style][0] = "CustomAppFont"
                    elif isinstance(self.theme_cls.font_styles[style], dict):
                        self.theme_cls.font_styles[style]["font-name"] = "CustomAppFont"
            except Exception as e:
                print("Font Load Error:", e)

    def update_all_views(self):
        self.update_dashboard()
        self.load_history()
        self.load_expenses()
        self.setup_month_filter_menu()
        self.setup_advanced_filters()

    def toggle_theme(self, active):
        self.theme_cls.theme_style = "Dark" if active else "Light"

    # ====== File Chooser & Cache Clean ======
    def open_file_chooser(self, mode):
        self.chooser_mode = mode
        if mode == "member": chooser = FileChooserIconView(filters=['*.png', '*.jpg', '*.jpeg'])
        elif mode == "font": chooser = FileChooserIconView(filters=['*.ttf', '*.otf'])
        else: chooser = FileChooserIconView(filters=['*.db'])
            
        chooser.bind(on_submit=self.file_selected)
        self.popup = Popup(title="Select File (Double Click)", content=chooser, size_hint=(0.9, 0.9))
        self.popup.open()

    def file_selected(self, chooser, selection, touch):
        if selection:
            if self.chooser_mode == "member":
                self.selected_image_path = selection[0]
                self.root.ids.img_preview.source = self.selected_image_path
            elif self.chooser_mode == "restore": 
                self.restore_db(selection[0])
            elif self.chooser_mode == "font": 
                self.set_custom_font(selection[0])
            self.popup.dismiss()

    def set_custom_font(self, file_path):
        try:
            shutil.copy(file_path, self.custom_font_path)
            self.apply_custom_font_if_exists()
            self.show_dialog("Success", "Custom Font Applied Successfully!\n(Some text might require an app restart).")
        except Exception as e: 
            self.show_dialog("Error", str(e))

    def clear_image_cache(self):
        members = self.db.get_all_members()
        active_images = [m[2] for m in members if m[2]]
        deleted_count = 0
        for filename in os.listdir("app_images"):
            filepath = f"app_images/{filename}"
            if filepath not in active_images:
                os.remove(filepath)
                deleted_count += 1
        self.show_dialog("Cache Cleared", f"{deleted_count} unused images deleted successfully!")

    # ====== Menus & Dropdowns ======
    def setup_menus(self):
        self.day_menu = MDDropdownMenu(caller=self.root.ids.input_day, items=[{"viewclass": "OneLineListItem", "text": str(i).zfill(2), "on_release": lambda x=str(i).zfill(2): self.set_menu_text("input_day", x, self.day_menu)} for i in range(1, 32)], width_mult=2)
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        self.month_menu = MDDropdownMenu(caller=self.root.ids.input_month, items=[{"viewclass": "OneLineListItem", "text": m, "on_release": lambda x=m: self.set_menu_text("input_month", x, self.month_menu)} for m in months], width_mult=2)
        current_year = datetime.now().year
        self.year_menu = MDDropdownMenu(caller=self.root.ids.input_year, items=[{"viewclass": "OneLineListItem", "text": str(y), "on_release": lambda x=str(y): self.set_menu_text("input_year", x, self.year_menu)} for y in range(current_year-2, current_year+5)], width_mult=2)

        cats = ["Ration / Grocery", "Utility Bills", "Room Rent", "Maintenance", "Medical", "Others"]
        self.category_menu = MDDropdownMenu(caller=self.root.ids.input_expense_category, items=[{"viewclass": "OneLineListItem", "text": c, "on_release": lambda x=c: self.set_menu_text("input_expense_category", x, self.category_menu)} for c in cats], width_mult=3)

        self.member_menu = MDDropdownMenu(caller=self.root.ids.input_member, items=[], width_mult=4)
        self.update_member_menu()
        self.amount_menu = MDDropdownMenu(caller=self.root.ids.input_amount, items=[], width_mult=2)
        self.update_amount_menu()

    def setup_advanced_filters(self):
        # 1. Sort Menu
        sorts = ["Newest First", "Oldest First", "Highest Amount"]
        s_items = [{"viewclass": "OneLineListItem", "text": s, "on_release": lambda x=s: self.apply_sort(x)} for s in sorts]
        if not self.sort_menu:
            self.sort_menu = MDDropdownMenu(caller=self.root.ids.btn_sort, items=s_items, width_mult=3)
        else:
            self.sort_menu.items = s_items
            
        # 2. Member Filter Menu
        members = self.db.get_all_members()
        m_items = [{"viewclass": "OneLineListItem", "text": "All Members", "on_release": lambda x="All Members": self.apply_member_filter(x)}]
        for m in members:
            m_items.append({"viewclass": "OneLineListItem", "text": m[1], "on_release": lambda x=m[1]: self.apply_member_filter(x)})
        if not self.member_filter_menu:
            self.member_filter_menu = MDDropdownMenu(caller=self.root.ids.btn_member_filter, items=m_items, width_mult=3)
        else:
            self.member_filter_menu.items = m_items

    def setup_month_filter_menu(self):
        # 3. Month Filter Menu
        months = self.db.get_unique_months()
        
        # Ensure current month is always present
        current_m = f"{datetime.now().strftime('%b')} {datetime.now().year}"
        if current_m not in months:
            months.append(current_m)
            
        items = [{"viewclass": "OneLineListItem", "text": "All Months", "on_release": lambda x="All Months": self.apply_month_filter(None)}]
        for m in months: 
            items.append({"viewclass": "OneLineListItem", "text": m, "on_release": lambda x=m: self.apply_month_filter(x)})
            
        if not self.month_filter_menu:
            self.month_filter_menu = MDDropdownMenu(caller=self.root.ids.btn_month_filter, items=items, width_mult=3)
        else:
            self.month_filter_menu.items = items

    def apply_sort(self, sort_text):
        self.current_sort_order = sort_text
        self.load_history(self.root.ids.search_field.text)
        self.sort_menu.dismiss()

    def apply_member_filter(self, member_name):
        self.current_member_filter = member_name
        self.load_history(self.root.ids.search_field.text)
        self.member_filter_menu.dismiss()

    def set_menu_text(self, field_id, text, menu):
        self.root.ids[field_id].text = text
        menu.dismiss()

    def apply_month_filter(self, month):
        self.current_filter_month = month
        self.root.ids.lbl_current_month_filter.text = month if month else "All Months"
        self.update_all_views()
        if self.month_filter_menu: self.month_filter_menu.dismiss()

    def update_member_menu(self):
        members = self.db.get_all_members()
        self.member_menu.items = [{"viewclass": "OneLineListItem", "text": m[1], "on_release": lambda x=m[1]: self.set_menu_text("input_member", x, self.member_menu)} for m in members]
        self.setup_advanced_filters()

    def update_amount_menu(self):
        amounts = self.db.get_default_amounts()
        self.amount_menu.items = [{"viewclass": "OneLineListItem", "text": str(amt), "on_release": lambda x=str(amt): self.set_menu_text("input_amount", x, self.amount_menu)} for a_id, amt in amounts]

    def open_week_dialog(self):
        self.selected_weeks.clear()
        content = MDBoxLayout(orientation='vertical', size_hint_y=None, height="350dp")
        scroll = MDScrollView()
        lst = MDList()
        weeks = ["Week 1", "Week 2", "Week 3", "Week 4", "Extra Fund", "Advance: Week 1", "Advance: Week 2", "Advance: Week 3", "Advance: Week 4"]
        for w in weeks: lst.add_widget(Factory.WeekListItem(text=w))
        scroll.add_widget(lst)
        content.add_widget(scroll)
        self.week_dialog = MDDialog(title="Select Week(s)", type="custom", content_cls=content, buttons=[MDFlatButton(text="OK", on_release=self.apply_weeks)])
        self.week_dialog.open()

    def on_week_check(self, active, text):
        if active and text not in self.selected_weeks: self.selected_weeks.append(text)
        elif not active and text in self.selected_weeks: self.selected_weeks.remove(text)

    def apply_weeks(self, *args):
        self.root.ids.input_week.text = f"{len(self.selected_weeks)} Items Selected" if self.selected_weeks else ""
        self.week_dialog.dismiss()

    def show_pending_dues(self):
        if not self.current_filter_month: return self.show_dialog("Info", "Please select a specific month first to check pending dues.")
        
        pending = self.db.get_pending_members(self.current_filter_month)
        content = MDBoxLayout(orientation='vertical', size_hint_y=None, height="300dp")
        scroll = MDScrollView()
        lst = MDList()
        if not pending: lst.add_widget(OneLineAvatarIconListItem(text="All clear! No pending dues."))
        else:
            for name, img in pending:
                item = OneLineAvatarIconListItem(text=name)
                if img and os.path.exists(img): item.add_widget(ImageLeftWidget(source=img))
                else: item.add_widget(IconLeftWidget(icon="account-alert"))
                lst.add_widget(item)
                
        scroll.add_widget(lst)
        content.add_widget(scroll)
        self.dialog = MDDialog(title=f"Pending Dues: {self.current_filter_month}", type="custom", content_cls=content, buttons=[MDFlatButton(text="CLOSE", on_release=lambda x: self.dialog.dismiss())])
        self.dialog.open()

    def confirm_delete_record(self, record_id, record_type):
        self.dialog = MDDialog(title="Delete Record?", text="کیا آپ واقعی اس انٹری کو ڈیلیٹ کرنا چاہتے ہیں؟", buttons=[MDFlatButton(text="CANCEL", on_release=lambda x: self.dialog.dismiss()), MDRaisedButton(text="DELETE", md_bg_color=(1, 0, 0, 1), on_release=lambda x: self.execute_delete_record(record_id, record_type))])
        self.dialog.open()

    def execute_delete_record(self, record_id, record_type):
        if record_type == "fund": self.db.delete_fund(record_id)
        elif record_type == "expense": self.db.delete_expense(record_id)
        self.dialog.dismiss()
        self.update_all_views()

    # ====== DB Tools & Backup ======
    def get_downloads_path(self): return os.path.join(os.path.expanduser('~'), 'Downloads')

    def export_to_csv(self):
        try:
            filename = os.path.join(self.get_downloads_path(), f"RoomFund_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Type", "Name / Description", f"Amount ({self.currency})", "Date", "Month", "Week Details", "Category"])
                funds = self.db.cursor.execute("SELECT members.name, funds.amount, funds.date, funds.month, funds.week FROM funds JOIN members ON funds.member_id = members.id").fetchall()
                for fund in funds: writer.writerow(["FUND IN", fund[0], fund[1], fund[2], fund[3], fund[4], "Income"])
                expenses = self.db.cursor.execute("SELECT description, amount, date, month, category FROM expenses").fetchall()
                for exp in expenses: writer.writerow(["EXPENSE OUT", exp[0], f"-{exp[1]}", exp[2], exp[3], "N/A", exp[4]])
            self.show_dialog("Success", f"Report saved to Downloads folder:\n{filename}")
        except Exception as e: self.show_dialog("Error", str(e))

    def backup_db(self, silent=False):
        try:
            dest = os.path.join(self.get_downloads_path(), f"RoomFund_Backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
            shutil.copy(self.db.db_name, dest)
            if not silent: self.show_dialog("Backup Successful", f"Database backed up to:\n{dest}")
        except Exception as e:
            if not silent: self.show_dialog("Error", str(e))

    def restore_db(self, filepath):
        try:
            self.db.conn.close() 
            shutil.copy(filepath, self.db.db_name) 
            self.db.connect_db() 
            self.update_all_views()
            self.show_dialog("Restore Successful", "Database restored successfully!")
        except Exception as e: self.show_dialog("Error", str(e))

    def confirm_factory_reset(self):
        self.dialog = MDDialog(title="FACTORY RESET?", text="خبردار! اس سے آپ کا سارا ڈیٹا ڈیلیٹ ہو جائے گا۔", buttons=[MDFlatButton(text="CANCEL", on_release=lambda x: self.dialog.dismiss()), MDRaisedButton(text="YES, DELETE ALL", md_bg_color=(1, 0, 0, 1), on_release=lambda x: self.execute_factory_reset())])
        self.dialog.open()

    def execute_factory_reset(self):
        self.db.reset_all_data()
        self.dialog.dismiss()
        self.update_all_views()
        self.show_dialog("Reset Complete", "All data has been erased. Start fresh!")

    def add_setting_amount(self):
        amt = self.root.ids.input_new_amount.text.strip()
        if amt and self.db.add_default_amount(amt):
            self.root.ids.input_new_amount.text = ""
            self.load_settings()
            self.update_amount_menu() 
        else: self.show_dialog("Error", "Invalid or existing amount!")

    def delete_setting_amount(self, a_id):
        self.db.delete_default_amount(a_id)
        self.load_settings()
        self.update_amount_menu()

    # ====== Core Actions ======
    def save_expense(self):
        desc = self.root.ids.input_expense_desc.text.strip()
        amt = self.root.ids.input_expense_amount.text.strip()
        cat = self.root.ids.input_expense_category.text.strip() or "General"
        
        if not desc or not amt: return self.show_dialog("Error", "Please enter Description and Amount!")
        
        date = datetime.now().strftime("%d-%b-%Y")
        month = f"{datetime.now().strftime('%b')} {datetime.now().year}"
        self.db.add_expense(desc, amt, date, month, cat)
        
        if self.db.get_config('auto_backup') == "1": self.backup_db(silent=True)
            
        self.show_dialog("Success", "Karch added successfully!")
        self.root.ids.input_expense_desc.text = ""
        self.root.ids.input_expense_amount.text = ""
        self.root.ids.input_expense_category.text = ""
        self.update_all_views()

    def load_expenses(self):
        e_list = self.root.ids.expenses_list
        e_list.clear_widgets()
        records = self.db.get_all_expenses(self.current_filter_month)
        
        icon_map = {"Ration / Grocery": "basket", "Utility Bills": "flash", "Room Rent": "home", "Maintenance": "hammer-wrench", "Medical": "hospital-box"}
        
        for e_id, desc, amount, date, cat in records:
            icon = icon_map.get(cat, "cart-minus")
            item = Factory.DeletableHistoryItem(record_id=e_id, record_type="expense", icon_left=icon, text=f"{desc} ({cat})  |  -{amount} {self.currency}", secondary_text=f"Date: {date}", icon_color=(1, 0.2, 0.2, 1))
            e_list.add_widget(item)

    def update_dashboard(self):
        income, expense, extra, members = self.db.get_dashboard_stats(self.current_filter_month)
        self.root.ids.lbl_total_income.text = f"{income:,} {self.currency}"
        self.root.ids.lbl_total_expense.text = f"{expense:,} {self.currency}"
        self.root.ids.lbl_total_members.text = str(members)
        self.root.ids.lbl_total_extra.text = f"{extra:,} {self.currency}"
        
        budget = int(self.db.get_config('budget_limit') or "0")
        if budget > 0 and expense > budget:
            self.root.ids.lbl_budget_warning.opacity = 1
            self.root.ids.lbl_budget_warning.height = "30dp"
            self.root.ids.lbl_budget_warning.text = f"⚠️ Warning: Monthly Budget of {budget} {self.currency} Exceeded!"
        else:
            self.root.ids.lbl_budget_warning.opacity = 0
            self.root.ids.lbl_budget_warning.height = "0dp"

    def load_history(self, search_text=""):
        history_list = self.root.ids.history_list
        history_list.clear_widgets()
        records = self.db.search_history(search_text, self.current_filter_month, self.current_member_filter, self.current_sort_order)
        for f_id, name, amount, date, week, f_type in records:
            icon = "cash-plus" if f_type == "Normal" else "star-circle"
            safe_color = getattr(self.theme_cls, 'primary_color', [0, 0.5, 0.5, 1])
            item = Factory.DeletableHistoryItem(record_id=f_id, record_type="fund", icon_left=icon, text=f"{name}  |  {amount} {self.currency}", secondary_text=f"{date}  |  {week}", icon_color=safe_color)
            history_list.add_widget(item)

    def load_manage_members(self):
        m_list = self.root.ids.manage_members_list
        m_list.clear_widgets()
        members = self.db.get_all_members()
        
        for m_id, m_name, m_image in members:
            total_given = self.db.get_member_total_fund(m_id)
            item = Factory.MemberListItem(
                member_id=m_id, 
                member_name=m_name, 
                image_src=m_image if (m_image and os.path.exists(m_image)) else "",
                text=m_name,
                secondary_text=f"Total Contributed: {total_given} {self.currency}"
            )
            m_list.add_widget(item)

    def show_total_members_popup(self):
        members = self.db.get_all_members()
        content = MDBoxLayout(orientation='vertical', size_hint_y=None, height="300dp")
        scroll = MDScrollView()
        lst = MDList()
        for m_id, m_name, m_image in members:
            total_given = self.db.get_member_total_fund(m_id)
            item = TwoLineAvatarIconListItem(text=m_name, secondary_text=f"Total: {total_given} {self.currency}")
            if m_image and os.path.exists(m_image): item.add_widget(ImageLeftWidget(source=m_image))
            else: item.add_widget(IconLeftWidget(icon="account"))
            lst.add_widget(item)
            
        scroll.add_widget(lst)
        content.add_widget(scroll)
        self.members_dialog = MDDialog(title="All Members & Stats", type="custom", content_cls=content, buttons=[MDFlatButton(text="CLOSE", on_release=lambda x: self.members_dialog.dismiss())])
        self.members_dialog.open()

    def confirm_delete_member(self, member_id, member_name):
        self.dialog = MDDialog(title="Delete Member?", text=f"کیا آپ واقعی '{member_name}' کو ڈیلیٹ کرنا چاہتے ہیں؟", buttons=[MDFlatButton(text="CANCEL", on_release=lambda x: self.dialog.dismiss()), MDRaisedButton(text="DELETE", md_bg_color=(1, 0, 0, 1), on_release=lambda x: self.execute_delete_member(member_id))])
        self.dialog.open()

    def execute_delete_member(self, member_id):
        self.db.delete_member(member_id)
        self.dialog.dismiss()
        self.update_member_menu()
        self.update_all_views()
        self.load_manage_members()

    def add_new_member(self):
        name = self.root.ids.input_new_member.text.strip()
        if not name: return self.show_dialog("Error", "Please enter a name!")
            
        final_image_path = ""
        if self.selected_image_path and os.path.exists(self.selected_image_path):
            ext = os.path.splitext(self.selected_image_path)[1]
            final_image_path = f"app_images/{name.replace(' ', '_')}{ext}"
            shutil.copy(self.selected_image_path, final_image_path)
            
        if self.db.add_member(name, final_image_path):
            self.show_dialog("Success", f"'{name}' Added Successfully!")
            self.root.ids.input_new_member.text = ""
            self.root.ids.img_preview.source = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
            self.selected_image_path = ""
            self.update_member_menu()
            self.update_all_views()
            self.load_manage_members()
        else: self.show_dialog("Error", "Name already exists!")

    def save_new_fund(self):
        member_name = self.root.ids.input_member.text.strip()
        day = self.root.ids.input_day.text.strip()
        month = self.root.ids.input_month.text.strip()
        year = self.root.ids.input_year.text.strip()
        amount_text = self.root.ids.input_amount.text.strip()
        
        if not all([member_name, self.selected_weeks, day, month, year, amount_text]): 
            return self.show_dialog("Error", "All fields are required!")

        date = f"{day}-{month}-{year}"
        base_amount = int(amount_text)
        
        members = self.db.get_all_members()
        member_id = next((m_id for m_id, m_name, m_img in members if m_name == member_name), None)
        if not member_id: return
            
        current_weeks, advance_weeks = [], []
        for w in self.selected_weeks:
            if "Advance:" in w: advance_weeks.append(w.replace("Advance: ", ""))
            else: current_weeks.append(w)
                
        current_month_str = f"{month} {year}"
        
        if current_weeks:
            total_current_amount = base_amount * len(current_weeks)
            week_str = ", ".join(current_weeks)
            fund_type = "Extra" if "Extra Fund" in week_str else "Normal"
            self.db.add_fund(member_id, current_month_str, week_str, date, total_current_amount, fund_type)
            
        if advance_weeks:
            months_list = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            current_index = months_list.index(month)
            if current_index == 11: 
                next_month, next_year = "Jan", str(int(year) + 1)
            else: 
                next_month, next_year = months_list[current_index + 1], year
                
            next_month_str = f"{next_month} {next_year}"
            total_adv_amount = base_amount * len(advance_weeks)
            adv_week_str = ", ".join(advance_weeks)
            self.db.add_fund(member_id, next_month_str, adv_week_str, f"{day}-{next_month}-{next_year}", total_adv_amount, "Normal")

        if self.db.get_config('auto_backup') == "1": self.backup_db(silent=True)

        self.show_dialog("Success", "Fund Saved Correctly!")
        self.root.ids.input_amount.text = ""
        self.root.ids.input_week.text = "" 
        self.selected_weeks.clear()
        self.update_all_views()
        self.load_manage_members()

    def show_dialog(self, title, text):
        if not self.dialog: 
            self.dialog = MDDialog(title=title, text=text, buttons=[MDFlatButton(text="OK", on_release=lambda x: self.dialog.dismiss())])
        else:
            self.dialog.title = title
            self.dialog.text = text
            self.dialog.buttons = [MDFlatButton(text="OK", on_release=lambda x: self.dialog.dismiss())]
        self.dialog.open()

if __name__ == "__main__":
    RoomFundApp().run()