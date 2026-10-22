# UbeKeso Cart

A responsive web app (it fills the whole browser window on computers, tablets and phones) for an ube cheese turon cart in Cebu City. Customers open the app and order right away, with **no login**. Staff and the owner sign in from **Settings**.

Built for the **Event-Driven Programming** final project. The app logic is Python (**PyScript** in the browser, plus a small standard-library Python server). There is no JavaScript logic.

## How to run

1. Install Python 3 (python.org). On Windows tick "Add python.exe to PATH" in the installer.
2. Open a terminal in this folder and run:

   ```
   python run.py
   ```

   (Some computers use `python3 run.py` or `py run.py`.)
3. The browser opens the app.

To try it on phones, run `python run.py --lan`, then open the address it prints (for example `http://192.168.1.20:8000/index.html`) on a phone on the same Wi-Fi. Orders placed on the phone appear on the staff screens within about 3 seconds.

Notes
- Internet is needed for PyScript and Google Fonts. Do not double-click `index.html`; use `run.py`.
- The app needs `run.py` (the server stores orders and accounts). It will not work on a static host such as GitHub Pages.

## What customers see

The first page is the landing page. There is nothing to sign in to.

1. The **advertisement video** (Watch: Ube-Kesoturon) plays at the top.
2. Below it the customer chooses pieces, extra cheese, pickup time and cash or e-wallet at pickup.
3. Tapping **Place order** asks for **name, mobile number and address**. The order is saved only after all three are filled in. The details are remembered on that phone so repeat orders are quicker.
4. The order then appears under **Your orders** at the top of the landing page and follows each step (Received, Frying, Ready, Done). Customers can cancel while it is still New.

Customers follow their orders on the same phone or browser they ordered from. Each order has a private tracking code saved in that browser, so nobody else can see or cancel it.

## Staff and owner sign in (Settings)

Tap **Settings** (top right of the landing page). It opens the staff and owner sign in.

| Who | How they get an account | What they see |
| --- | --- | --- |
| **Owner (admin)** | Created automatically the first time the server starts | Everything: Home dashboard with "Needs attention", all orders, Staff accounts and activity log, Stock, Loyalty, Reports |
| **Staff** | Created by the owner on the Staff tab (the + button), with a Gmail address | Home, Sell, Orders, Loyalty, Stock (no Reports, no staff list) |

**Owner login (first run):** `admin@ubekeso.ph` / `Admin#2026`. The app shows a "Change your password" banner until you change it. To use your own from the start, set `UBEKESO_ADMIN_EMAIL` and `UBEKESO_ADMIN_PASSWORD` before the first run.

Sign in is rate limited (5 wrong tries = 1 minute wait). **Forgot password?** emails a 6-digit code (see below).

## The live order flow

1. A customer places an order. It is saved with their name, mobile number and address.
2. Staff and the owner see it in **Orders** with a red badge on the tab and a "New order from ..." message. **Details** shows the mobile number and address.
3. Staff tap **Start frying**, **Mark ready**, then **Picked up and paid**. The customer's screen follows each step and shows a message when it is ready.
4. The owner sees every order, who started it, and the activity log of what each staff member did and when (the owner can delete single entries or clear the log). The Staff tab also shows who is online right now.
5. When an order is picked up, it is added to today's sales and a loyalty stamp is added to the card kept under the customer's mobile number (a card is created the first time).

## Logo, About us & FAQs, and the promo video

- **Logo:** your Ube-Kesoturon picture is used on the landing page, Settings, the About page, and as the browser icon. The files are in `media/` (`logo.jpg`, `logo-small.jpg`, `logo-icon.png`).
- **About us & FAQs:** a page anyone can open from the landing page. The questions are written in `faq_items()` in `main.py`; prices and the number of stamps update by themselves from `server.py`.
- **Advertisement video:** it is the first thing on the landing page and plays muted and looping (customers can use the controls to unmute). Save your video as `media/promo.mp4` (`promo.webm` or `promo.mov` also work) and refresh the page. No restart is needed. Until the file exists the page shows a "Promo video coming soon" box. Keep the video short and compressed (under about 30 MB) so it loads quickly on phones.

## Emailed codes (staff password reset)

Staff accounts must use a Gmail address. Password reset codes are emailed from a Gmail account that you set up once:

1. Use a Gmail account for the cart (for example `ubekesocart@gmail.com`). Turn on **2-Step Verification** in its Google Account.
2. In Google Account > Security > **App passwords**, create one named "UbeKeso Cart". Google shows a 16-letter password.
3. Copy `mail_settings.example.json` to `mail_settings.json` and fill it in:

   ```
   { "gmail_address": "ubekesocart@gmail.com", "app_password": "abcd efgh ijkl mnop" }
   ```
4. Restart `python run.py`. It prints "Gmail sending is ON".

`mail_settings.json` is never sent to browsers. Do not share it or upload it to GitHub. Instead of the file you can set the environment variables `UBEKESO_SMTP_USER` and `UBEKESO_SMTP_PASSWORD`.

Until this is set up the app runs in **demo mode**: the code is shown inside the app so you can still test.

## Your data is always saved

Every change (orders with customer details, accounts, stock, stamps, sales) is written to `data.json` on the computer that runs `run.py`, right away, and forced onto the disk. It stays there when people sign out, when phones go offline, when the browser closes and when you stop and restart the server.

- Writes are crash-safe (a temporary file is swapped in), so a power cut cannot leave a half-written file.
- A copy of `data.json` is kept every day in the `backups/` folder (last 14 days). If `data.json` is ever damaged, the newest backup is restored automatically on start.
- `python reset_data.py` copies your old data to `backups/` before wiping it.
- If a phone loses Wi-Fi, the app reconnects by itself. An order sent while offline does not go through; the app shows "Connection lost" and the customer taps again once back online.
- The computer running `run.py` must be on for the app to open. To use it from anywhere, run it on an always-on computer or a hosting service.

## Start fresh (reset the database)

To wipe everything (for example before your presentation), stop the server with Ctrl+C and run:

```
python reset_data.py
```

Type `YES` when asked (or use `python reset_data.py --yes`). Your logo and promo video in `media/` are not touched.

## Files

| File | What it does |
| --- | --- |
| `index.html` | Page shell and PyScript loader |
| `style.css`, `extra.css` | Styles |
| `main.py` | The app in the browser: state, screens, event handlers, live polling |
| `server.py` | Backend: public orders, staff and owner accounts, orders, activity log, saving to `data.json` |
| `run.py` | Starts the server and opens the browser |
| `reset_data.py` | Erases all data and starts the database fresh |
| `media/` | Logo pictures and your promo video (`promo.mp4`) |
| `pyscript.toml` | PyScript config |
| `data.json` | Created on first run; all orders, accounts and stock |
| `backups/` | Daily copies of `data.json` (last 14 days) |
| `mail_settings.json` | Your sending Gmail + App password (you create it) |

## Event-Driven Programming in `main.py`

| Event | Where | Handler |
| --- | --- | --- |
| `click` (event delegation on `data-action`) | all buttons, tabs, steppers, chips | `on_click` -> `CLICK_ACTIONS` |
| `submit` | customer details, staff sign in, forgot and reset password, change password, new card, pre-order, stock, new staff | `on_submit` -> `SUBMIT_HANDLERS` |
| `input` | Loyalty search box | `on_input` |
| `change` | Extra cheese switch (sale and customer order), pickup time | `on_change` |
| `keydown` | Escape closes a form sheet | `on_keydown` |
| `setInterval` timer, every 3 s | live updates: customers refresh their order status, staff ask the server what changed | `on_tick` -> `poll` |
| `visibilitychange` | refreshes at once when you return to the tab | `on_visible` |
| `setTimeout` timer | toast message hides itself | `toast` |

The screen is never redrawn while someone is typing in a field or has a form open; the update is applied right after.

## Security notes

- Passwords are stored only as salted PBKDF2-SHA256 hashes.
- Every staff and owner action is checked on the server by role. Public visitors can only place an order, look up their own orders with their private tracking code and cancel their own New orders.
- Orders are limited per mobile number (5 waiting) and per device (20 per 10 minutes).
- `server.py`, `run.py`, `reset_data.py` and `data.json` are never served to browsers. Only pictures and videos inside `media/` are shared.
- Running over plain HTTP on your own Wi-Fi is fine for a school project. For a public deployment use HTTPS and a real database.

## Things you can change

At the top of `server.py` (`CONFIG`): `price`, `extra_cheese_price` (5 is a placeholder; set your real price), `daily_target`, `month_goal`, `cost_per_piece`, stamps for a free piece, low-stock levels and minimum password length. The app picks them up automatically.
