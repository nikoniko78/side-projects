import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from urllib.request import Request, urlopen
from urllib.parse import quote, unquote, urljoin
import threading, re, os, time, json, html
from PIL import Image, ImageTk
import requests

IMG_FOLDER = "wiki_images"
os.makedirs(IMG_FOLDER, exist_ok=True)
SETTINGS_FILE = "settings.json"
HISTORY_FILE = os.path.join(IMG_FOLDER, "history.json")
LAST10_FILE = os.path.join(IMG_FOLDER, "last10.json")
RECENT_MAX = 100

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {"dark_mode": False}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def save_history(url):
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
    except:
        history = []
    if url in history:
        history.remove(url)
    history.append(url)
    if len(history) > RECENT_MAX:
        history = history[-RECENT_MAX:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)
    last10 = history[-10:]
    with open(LAST10_FILE, "w") as f:
        json.dump(last10, f)

def check_internet():
    try:
        req = Request("https://en.wikipedia.org/wiki/Main_Page", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception as e:
        print("Internet check failed:", e)
        return False

class WikiBrowser:
    def __init__(self, root):
        self.online = check_internet()
        self.root = root
        self.root.title("pyDesk: General Information Utility")
        self.root.geometry("1200x600")
        ctk.set_default_color_theme("blue")
        self.toc_widget_map = {}
        self.settings = load_settings()
        self.translator_panel_active = False

        # --- Top bar ---
        self.top_frame = ctk.CTkFrame(root)
        self.top_frame.pack(fill="x", pady=5)
        self.entry = ctk.CTkEntry(self.top_frame, placeholder_text="Search Wikipedia")
        self.entry.pack(side="left", fill="x", expand=True, padx=5)
        self.entry.bind("<Return>", lambda e: self.search())
        self.btn = ctk.CTkButton(self.top_frame, text="Search", command=self.search)
        self.btn.pack(side="left", padx=5)
        self.dark_btn = ctk.CTkButton(self.top_frame, text="Toggle Dark Mode", command=self.toggle_dark_mode)
        self.dark_btn.pack(side="left", padx=5)
        self.back_btn = ctk.CTkButton(self.top_frame, text="Back", command=self.go_back, state="disabled")
        self.back_btn.pack(side="left", padx=5)
        self.back_stack = []

        # --- Main frame ---
        main_frame = ctk.CTkFrame(root)
        main_frame.pack(fill="both", expand=True)

        # TOC frame
        self.toc_frame = ctk.CTkFrame(main_frame, width=250)
        self.toc_frame.pack(side="left", fill="y")
        self.toc_label = ctk.CTkLabel(self.toc_frame, text="Table of Contents", font=("Arial", 12, "bold"))
        self.toc_label.pack(pady=5)
        # keep ttk.Treeview if you want hierarchical TOC
        self.toc_tree = ttk.Treeview(self.toc_frame)
        self.toc_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.toc_tree.bind("<<TreeviewSelect>>", self.scroll_to_section)
        self.toc_positions = []

        # Scrollable article area
        import tkinter as tk  # make sure this import is at the top of your file
        self.canvas = tk.Canvas(main_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ctk.CTkFrame(self.canvas)
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="left", fill="y")
        self._enable_mouse_scroll()

        # Loading animation
        self.loading_label = ctk.CTkLabel(root, text="", font=("Arial", 14))
        self.animate_loading = False

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(root, width=1200)
        self.progress_bar.pack(fill="x", pady=2)
        self.progress_bar.set(0)

        self.current_url = None

        if self.online:
            self.tool_selector = ctk.CTkOptionMenu(
                self.top_frame,
                values=["Wikipedia", "Dictionary", "Thesaurus", "Translate", "Notes"],
                command=self.set_mode
            )
            self.tool_selector.set("Wikipedia")
            self.tool_selector.pack(side="left", padx=5)
        self.current_mode = "Wikipedia"

        # --- Now safe to apply colors ---
        self.set_colors()

        # --- Startup behavior ---
        if self.online:
            self.show_welcome_screen()
        else:
            self.enable_offline_search_suggestions()            
            self.show_offline_grid()

    def set_mode(self, mode):
        self.current_mode = mode

        mode_colors = {
            "Wikipedia": {"bg": "#1f6aa5", "text": "white"},
            "Dictionary": {"bg": "#2e8b57", "text": "white"},
            "Thesaurus": {"bg": "#d2691e", "text": "white"},
            "Translate": {"bg": "#6a5acd", "text": "white"},
            "Notes": {"bg": "#c62828", "text": "white"}
        }
        color = mode_colors.get(mode, {"bg": "#1f6aa5", "text": "white"})
        bg_color = color["bg"]
        text_color = color["text"]

        for btn in [self.btn, self.dark_btn, self.back_btn]:
            btn.configure(fg_color=bg_color, text_color=text_color)
        self.tool_selector.configure(
            fg_color=bg_color,
            text_color=text_color,
            button_color=bg_color,
            button_hover_color=bg_color
        )

        self.clear_old()

        # Rebind <Return> based on mode
        if mode == "Translate":
            self.entry.unbind("<Return>")
            self.entry.bind("<Return>", lambda e: self.show_translator_panel())
            self.show_translator_panel()
        elif mode == "Dictionary":
            self.entry.unbind("<Return>")
            self.entry.bind("<Return>", lambda e: self.show_dictionary_panel())
            self.show_dictionary_panel()
        elif mode == "Thesaurus":
            self.entry.unbind("<Return>")
            self.entry.bind("<Return>", lambda e: self.show_thesaurus_panel())
            self.show_thesaurus_panel()
        elif mode in ["Wikipedia"]:
            self.entry.unbind("<Return>")
            self.entry.bind("<Return>", lambda e: self.search())
        elif mode == "Notes":
            self.entry.unbind("<Return>")
            self.entry.bind("<Return>", lambda e: self.show_notes_panel())
            self.show_notes_panel()

    def show_thesaurus_panel(self):
        self.clear_old()
        self.entry.configure(state="normal")
        self.entry.unbind("<Return>")
        self.entry.bind("<Return>", lambda e: self.show_thesaurus_panel())

        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.pack_forget()

        panel = ctk.CTkFrame(
            self.scrollable_frame,
            corner_radius=0,
            fg_color=self.scrollable_frame.cget("fg_color")
        )
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(panel, text="Thesaurus", font=("Arial", 16, "bold")).pack(pady=10)

        term = self.entry.get().strip()
        if term:
            self._lookup_thesaurus(term, panel)
        else:
            ctk.CTkLabel(panel, text="Type a word above and press Enter.", font=("Arial", 13)).pack(pady=10)

    def _lookup_thesaurus(self, word, panel):
        try:
            syn_url = f"https://api.datamuse.com/words?rel_syn={quote(word)}"
            ant_url = f"https://api.datamuse.com/words?rel_ant={quote(word)}"

            syn_response = requests.get(syn_url, verify=False)
            ant_response = requests.get(ant_url, verify=False)

            synonyms = [item["word"] for item in syn_response.json()]
            antonyms = [item["word"] for item in ant_response.json()]

            output = f"Synonyms for '{word}':\n"
            output += ", ".join(synonyms[:15]) if synonyms else "None found."
            output += "\n\nAntonyms:\n"
            output += ", ".join(antonyms[:15]) if antonyms else "None found."

            ctk.CTkLabel(
                panel,
                text=output,
                font=("Arial", 13),
                wraplength=900,
                justify="left",
                anchor="w"
            ).pack(fill="both", expand=True)

        except Exception as e:
            ctk.CTkLabel(
                panel,
                text=f"Error: {str(e)}",
                font=("Arial", 13),
                wraplength=900,
                justify="left",
                anchor="w"
            ).pack(fill="both", expand=True)

    def set_colors(self):
        style = ttk.Style()
        style.theme_use("clam")  # ensure ttk respects custom colors
        if self.settings["dark_mode"]:
            ctk.set_appearance_mode("Dark")
            style.configure("Treeview", background="#2b2b2b", foreground="white", fieldbackground="#2b2b2b")
            style.map("Treeview", background=[("selected", "#444444")])
            style.configure("Vertical.TScrollbar", background="#2b2b2b", troughcolor="#2b2b2b")
            style.configure("TProgressbar", background="#3399FF", troughcolor="#2b2b2b")
            self.canvas.configure(bg="#2b2b2b", highlightthickness=0)
            self.scrollable_frame.configure(fg_color="#2b2b2b")
        else:
            ctk.set_appearance_mode("Light")
            style.configure("Treeview", background="white", foreground="black", fieldbackground="white")
            style.map("Treeview", background=[("selected", "#cccccc")])
            style.configure("Vertical.TScrollbar", background="white", troughcolor="white")
            style.configure("TProgressbar", background="#3399FF", troughcolor="white")
            self.canvas.configure(bg="white")
            self.scrollable_frame.configure(fg_color="white")

    def _real_translate(self, textbox, from_lang, to_lang):
        text = textbox.get("1.0", "end").strip()
        if not text:
            textbox.delete("1.0", "end")
            textbox.insert("end", "\nPlease enter text to translate.")
            return

        lang_map = {
            "Auto Detect": "auto", "English": "en", "Spanish": "es", "French": "fr", "German": "de", "Chinese": "zh-CN",
            "Arabic": "ar", "Russian": "ru", "Hindi": "hi", "Japanese": "ja", "Korean": "ko",
            "Turkish": "tr", "Portuguese": "pt", "Italian": "it", "Dutch": "nl", "Polish": "pl",
            "Ukrainian": "uk", "Vietnamese": "vi", "Hebrew": "iw", "Indonesian": "id", "Filipino": "tl",
            "Czech": "cs", "Greek": "el", "Swedish": "sv", "Finnish": "fi", "Norwegian": "no",
            "Danish": "da", "Hungarian": "hu", "Romanian": "ro", "Thai": "th", "Malay": "ms",
            "Slovak": "sk", "Bulgarian": "bg", "Serbian": "sr", "Croatian": "hr", "Persian": "fa",
            "Urdu": "ur", "Swahili": "sw", "Tamil": "ta", "Telugu": "te", "Kannada": "kn"
        }

        source = lang_map.get(from_lang, "auto")
        target = lang_map.get(to_lang, "en")

        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source}&tl={target}&dt=t&q={requests.utils.quote(text)}"
            response = requests.get(url)
            data = response.json()
            translated = "".join([chunk[0] for chunk in data[0]]) if data and data[0] else "Translation failed."
            textbox.delete("1.0", "end")
            textbox.insert("end", translated)
        except Exception as e:
            textbox.delete("1.0", "end")
            textbox.insert("end", f"Error: {str(e)}")

    def toggle_dark_mode(self):
        self.settings["dark_mode"] = not self.settings["dark_mode"]
        save_settings(self.settings)
        self.set_colors()

    def show_welcome_screen(self):
        self.clear_old()

        # turn off scrolling so the welcome screen is fixed
        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.pack_forget()

        panel = ctk.CTkFrame(
            self.scrollable_frame,
            fg_color=self.scrollable_frame.cget("fg_color"),
            corner_radius=0,
            border_width=0
        )
        panel.pack(fill="both", expand=True, padx=0, pady=0)

        lbl = ctk.CTkLabel(
            panel,
            text=(
                "Welcome to pyDesk!\n\n"
                "Type a topic in the search bar above and press Enter.\n"
                "Use the tab in the top right corner to change tools.\n"
                "You are currently in Wikipedia mode."
            ),
            font=("Arial", 14),
            justify="center",   # center text lines
            anchor="center",    # center the widget content
            wraplength=800      # prevent text from being squashed
        )
        # expand=True makes the label fill the panel,
        # and it will stay centered both vertically and horizontally
        lbl.pack(expand=True, fill="both")

    def show_downloaded_articles(self):
        self.clear_old()
        self.entry.configure(state="disabled")
        self.btn.configure(state="disabled")

        panel = ctk.CTkFrame(self.scrollable_frame, fg_color=self.scrollable_frame.cget("fg_color"))
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(panel, text="Offline Mode: Search downloaded articles", font=("Arial", 14)).pack(pady=10)

        grid_frame = ctk.CTkScrollableFrame(panel)
        grid_frame.pack(fill="both", expand=True, padx=10, pady=10)

        files = [f for f in os.listdir(IMG_FOLDER) if f.endswith(".html")]
        label_widgets = []

        def update_grid(filter_text=""):
            for lbl in label_widgets:
                lbl.destroy()
            label_widgets.clear()

            filtered = [f for f in files if filter_text.lower() in f.lower()]
            cols = 8
            for idx, f in enumerate(filtered):
                article_name = os.path.splitext(f)[0]
                lbl = ctk.CTkLabel(grid_frame, text=article_name, font=("Arial", 13),
                                   anchor="w", justify="left", cursor="hand2")
                r, c = divmod(idx, cols)
                lbl.grid(row=r, column=c, padx=10, pady=10, sticky="w")

                # Make label clickable
                lbl.bind("<Button-1>", lambda e, fn=f: self._open_cached_article(fn))
                label_widgets.append(lbl)

        update_grid("")

    def show_notes_panel(self):
        self.clear_old()
        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.pack_forget()

        notes_dir = os.path.join(IMG_FOLDER, "notes")
        os.makedirs(notes_dir, exist_ok=True)

        panel = ctk.CTkFrame(self.scrollable_frame, corner_radius=0, fg_color=self.scrollable_frame.cget("fg_color"))
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(panel, text="Notes", font=("Arial", 16, "bold")).pack(pady=10)

        content_frame = ctk.CTkFrame(panel)
        content_frame.pack(fill="both", expand=True)

        file_list_frame = ctk.CTkFrame(content_frame, width=200)
        file_list_frame.pack(side="left", fill="y", padx=5, pady=5)

        file_label = ctk.CTkLabel(file_list_frame, text="Files", font=("Arial", 13, "bold"))
        file_label.pack(pady=5)

        control_frame = ctk.CTkFrame(file_list_frame)
        control_frame.pack(pady=5)

        file_buttons = []
        current_file = [None]
        last_saved_content = [""]
        last_edit_time = [0]

        editor_frame = ctk.CTkFrame(content_frame)
        editor_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        title_entry = ctk.CTkEntry(editor_frame, placeholder_text="Note Title", font=("Arial", 13))
        title_entry.pack(fill="x", padx=10, pady=(10, 0))

        textbox = tk.Text(editor_frame, wrap="word", font=("Arial", 12), height=12)
        textbox.pack(fill="x", padx=10, pady=(5, 10), ipady=75)

        def load_file(filename):
            save_file()
            current_file[0] = filename
            textbox.delete("1.0", "end")
            title_entry.delete(0, "end")
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        title_entry.insert(0, lines[0].strip())
                        textbox.insert("end", "".join(lines[1:]))
                        last_saved_content[0] = "".join(lines)

            refresh_file_list()


        def refresh_file_list():
            for btn in file_buttons:
                btn.destroy()
            file_buttons.clear()

            files = [f for f in os.listdir(notes_dir) if f.endswith(".txt")]
            for fname in files:
                full_path = os.path.join(notes_dir, fname)
                is_selected = current_file[0] and os.path.basename(current_file[0]) == fname

                raw_title = fname[:-4] if fname.endswith(".txt") else fname
                display_title = raw_title[:15] + "..." if len(raw_title) > 15 else raw_title

                btn = ctk.CTkButton(
                    file_list_frame,
                    text=display_title,
                    corner_radius=8,
                    width=140,
                    height=28,
                    text_color="white",
                    fg_color="#800000" if is_selected else "#c62828",
                    hover_color="#a00000",
                    command=lambda f=full_path: load_file(f)
                )
                btn.pack(fill="x", pady=2)
                file_buttons.append(btn)

        def confirm_delete():
            from tkinter import messagebox
            if current_file[0] and messagebox.askyesno("Delete Note", f"Are you sure you want to delete '{os.path.basename(current_file[0])}'?"):
                os.remove(current_file[0])
                textbox.delete("1.0", "end")
                title_entry.delete(0, "end")
                current_file[0] = None
                refresh_file_list()

        def save_file():
            if not current_file[0]:
                return

            title = title_entry.get().strip() or "untitled"
            body = textbox.get("1.0", "end").strip()
            content = title + "\n" + body

            old_path = current_file[0]
            safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)
            new_path = os.path.join(notes_dir, f"{safe_title}.txt")

            if content != last_saved_content[0] or old_path != new_path:
                with open(new_path, "w", encoding="utf-8") as f:
                    f.write(content)
                last_saved_content[0] = content
                if old_path != new_path and os.path.exists(old_path):
                    os.remove(old_path)
                current_file[0] = new_path
                refresh_file_list()

        def autosave_loop():
            while True:
                time.sleep(1)
                if time.time() - last_edit_time[0] >= 1:
                    save_file()

        def on_edit(event):
            last_edit_time[0] = time.time()

        textbox.bind("<Key>", on_edit)
        title_entry.bind("<Key>", on_edit)
        threading.Thread(target=autosave_loop, daemon=True).start()

        def new_file():
            term = self.entry.get().strip() or "untitled"
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", term)
            filename = os.path.join(notes_dir, f"{safe_name}_{timestamp}.txt")
            with open(filename, "w", encoding="utf-8") as f:
                f.write("")
            refresh_file_list()
            load_file(filename)

        new_btn = ctk.CTkButton(control_frame, text="New Note", fg_color="#c62828", command=new_file)
        new_btn.pack(pady=2)

        del_btn = ctk.CTkButton(control_frame, text="Delete", fg_color="#c62828", command=confirm_delete)
        del_btn.pack(pady=2)

        refresh_file_list()

    def _open_cached_article(self, filename):
        self.entry.configure(state="normal")
        self.btn.configure(state="normal")
        local_file = os.path.join(IMG_FOLDER, filename)
        with open(local_file, "r", encoding="utf-8") as f:
            html_content = f.read()
        self.current_url = f"cached://{filename}"
        save_history(self.current_url)
        headings = re.findall(r'<h([1-6]).*?id="([^"]+)".*?>(.*?)</h[1-6]>', html_content, re.DOTALL)
        paragraphs = re.findall(r'<p>(.*?)</p>', html_content, re.DOTALL)
        self._display_article_one_by_one(paragraphs, headings, html_content)
    # ---------------- Mouse Scroll ----------------
    def _enable_mouse_scroll(self):
        def _on_mousewheel(event):
            if event.delta:
                self.canvas.yview_scroll(-1 * (event.delta // 120), "units")
            else:
                if event.num == 4:
                    self.canvas.yview_scroll(-2, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(2, "units")
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.canvas.bind_all("<Button-4>", _on_mousewheel)
        self.canvas.bind_all("<Button-5>", _on_mousewheel)

    # ---------------- TOC ----------------
    def scroll_to_section(self, event):
        selected = self.toc_tree.focus()
        widget = self.toc_widget_map.get(selected)
        if widget:
            self.root.update_idletasks()
            y = widget.winfo_y()
            total = max(1, self.scrollable_frame.winfo_height())
            self.canvas.yview_moveto(y / total)
    # ---------------- Clear / Loading ----------------
    def clear_old(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        for i in self.toc_tree.get_children():
            self.toc_tree.delete(i)
        self.toc_positions.clear()
        self.progress_bar.set(0)
        self.canvas.yview_moveto(0)

    def start_loading(self):
        self.animate_loading = True
        self.loading_label.pack(pady=5)
        threading.Thread(target=self._loading_animation, daemon=True).start()

    def stop_loading(self):
        self.animate_loading = False
        self.loading_label.pack_forget()
        self.progress_bar.set(0)

    def _loading_animation(self):
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        i = 0
        while self.animate_loading:
            self.loading_label.configure(text=f"Loading {frames[i % len(frames)]}")
            i += 1
            time.sleep(0.1)
    # ---------------- Navigation ----------------
    def go_back(self):
        if not self.back_stack:
            self.back_btn.configure(state="disabled")
            return
        prev_url = self.back_stack.pop()
        if not self.back_stack:
            self.back_btn.configure(state="disabled")
        self.search(prev_url)

    # ---------------- Search ----------------
    def search(self, url=None):
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        term = self.entry.get().strip()
        if not term and not url:
            return

        self.clear_old()
        self.start_loading()

        if self.current_mode == "Wikipedia":
            if not url:
                url_term = quote(term.replace(" ", "_"))
                url = f"https://en.wikipedia.org/wiki/{url_term}"
            self.current_url = url
            save_history(url)
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", url.split("/")[-1])
            local_file = os.path.join(IMG_FOLDER, f"{safe_name}.html")
            if os.path.exists(local_file):
                with open(local_file, "r", encoding="utf-8") as f:
                    html_content = f.read()
                headings = re.findall(r'<h([1-6]).*?id="([^"]+)".*?>(.*?)</h[1-6]>', html_content, re.DOTALL)
                paragraphs = re.findall(r'<p>(.*?)</p>', html_content, re.DOTALL)
                paragraphs = paragraphs[:5]
                self.root.after(0, lambda: self._display_article_one_by_one(paragraphs, headings, html_content))
                self.stop_loading()
            else:
                threading.Thread(target=self._fetch_article, args=(url, False), daemon=True).start()

        elif self.current_mode == "Dictionary":
                self.canvas.unbind_all("<MouseWheel>")
                self.scrollbar.pack_forget()

                panel = ctk.CTkFrame(self.scrollable_frame, corner_radius=0, fg_color=self.scrollable_frame.cget("fg_color"))
                panel.pack(fill="both", expand=True, padx=20, pady=20)

                ctk.CTkLabel(panel, text="Dictionary", font=("Arial", 16, "bold")).pack(pady=10)

                try:
                        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{term}"
                        response = requests.get(url, verify=False)
                        data = response.json()

                        if isinstance(data, dict) and data.get("title") == "No Definitions Found":
                                ctk.CTkLabel(panel, text=f"No definition found for '{term}'", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(pady=10)
                                self._lookup_urban_dictionary(term, panel)
                        else:
                                meanings = data[0].get("meanings", [])
                                content = f"Definitions for '{term}':\n\n"
                                for meaning in meanings:
                                        pos = meaning.get("partOfSpeech", "")
                                        for definition in meaning.get("definitions", []):
                                                text = definition.get("definition", "")
                                                example = definition.get("example", "")
                                                content += f"• ({pos}) {text}\n"
                                                if example:
                                                        content += f"    e.g. {example}\n"
                                ctk.CTkLabel(panel, text=content.strip(), font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(fill="both", expand=True)
                except Exception as e:
                        ctk.CTkLabel(panel, text=f"Error: {str(e)}", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(fill="both", expand=True)

                self.stop_loading()

    def _lookup_urban_dictionary(self, term, panel):
        try:
            ctk.CTkLabel(panel, text=f"No definition found for '{term}'.", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(pady=10)
        except Exception as e:
            ctk.CTkLabel(panel, text=f"Error: {str(e)}", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(pady=10)

    def show_full_article(self):
        if self.current_url:
            self.clear_old()
            self.start_loading()
            safe_name = re.sub(r'[\\/*?:"<>|]', "_", self.current_url.split("/")[-1])
            local_file = os.path.join(IMG_FOLDER, f"{safe_name}.html")
            if os.path.exists(local_file):
                with open(local_file, "r", encoding="utf-8") as f:
                    html_content = f.read()
                headings = re.findall(r'<h([1-6]).*?id="([^"]+)".*?>(.*?)</h[1-6]>', html_content, re.DOTALL)
                paragraphs = re.findall(r'<p>(.*?)</p>', html_content, re.DOTALL)
                self.root.after(0, lambda: self._display_article_one_by_one(paragraphs, headings, html_content))
                self.stop_loading()
            else:
                threading.Thread(target=self._fetch_article, args=(self.current_url, True), daemon=True).start()
    def _fetch_article(self, url, full=False):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=10) as response:
                html_content = response.read().decode("utf-8", errors="ignore")
        except Exception as e:
            self._display_error(str(e))
            return

        html_content = html.unescape(html_content)

        safe_name = re.sub(r'[\\/*?:"<>|]', "_", url.split("/")[-1])
        local_file = os.path.join(IMG_FOLDER, f"{safe_name}.html")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        headings = re.findall(r'<h([1-6]).*?id="([^"]+)".*?>(.*?)</h[1-6]>', html_content, re.DOTALL)
        paragraphs = re.findall(r'<p>(.*?)</p>', html_content, re.DOTALL)

        if not full:
            paragraphs = paragraphs[:5]

        self.root.after(0, lambda: self._display_article_one_by_one(paragraphs, headings, html_content))

    def show_offline_grid(self):
        self.clear_old()

        # turn off scrolling
        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.pack_forget()

        panel = ctk.CTkFrame(
            self.scrollable_frame,
            fg_color=self.scrollable_frame.cget("fg_color"),
            corner_radius=0
        )
        panel.pack(fill="both", expand=True)

        title = ctk.CTkLabel(panel, text="Offline Articles",
                             font=("Arial", 16, "bold"), anchor="center")
        title.pack(pady=10)

        grid_frame = ctk.CTkFrame(panel, corner_radius=0)
        grid_frame.pack(expand=True, fill="both")

        files = [f for f in os.listdir(IMG_FOLDER) if f.endswith(".html")]
        files.sort(key=lambda x: x.lower())

        label_widgets = []

        def update_grid(filter_text=""):
            for lbl in label_widgets:
                lbl.destroy()
            label_widgets.clear()

            filtered = [f for f in files if filter_text.lower() in f.lower()]
            cols = 8
            for idx, f in enumerate(filtered):
                article_name = os.path.splitext(f)[0]
                lbl = ctk.CTkLabel(grid_frame, text=article_name,
                                   font=("Arial", 13),
                                   anchor="center", justify="center")
                r, c = divmod(idx, cols)
                lbl.grid(row=r, column=c, padx=20, pady=10, sticky="nsew")
                label_widgets.append(lbl)

            for c in range(cols):
                grid_frame.grid_columnconfigure(c, weight=1)

        def on_key(event):
            query = self.entry.get().strip()
            update_grid(query)

        self.entry.bind("<KeyRelease>", on_key)
        update_grid("")

    def enable_offline_search_suggestions(self):
        self.entry.configure(state="normal")
        self.btn.configure(state="disabled")

        # Offline instruction label
        self.offline_label = ctk.CTkLabel(self.top_frame,
            text="Offline Mode: Type to search downloaded articles",
            font=("Arial", 12), text_color="#888888")
        self.offline_label.pack(side="right", padx=10)

        # "List" button to return to offline grid
        self.list_btn = ctk.CTkButton(self.top_frame, text="List",
                                      command=self.show_offline_grid)
        self.list_btn.pack(side="right", padx=5)

        # Suggestion dropdown (unchanged)
        bg = "#f2f6ff" if ctk.get_appearance_mode() == "Light" else "#1b1f26"
        self.suggestion_frame = ctk.CTkFrame(self.root, fg_color=bg,
                                             corner_radius=10,
                                             border_color="#1f6aa5",
                                             border_width=1)
        self.suggestion_frame.place_forget()
        self.suggestion_labels = []
        self.selected_index = -1

        def update_suggestions(event=None):
            query = self.entry.get().strip().lower()
            for lbl in self.suggestion_labels:
                lbl.destroy()
            self.suggestion_labels.clear()
            self.selected_index = -1

            if not query:
                self.suggestion_frame.place_forget()
                return

            files = [f for f in os.listdir(IMG_FOLDER) if f.endswith(".html")]
            matches = [f for f in files if query in f.lower()]
            if not matches:
                self.suggestion_frame.place_forget()
                return

            self.suggestion_frame.place(
                x=self.entry.winfo_rootx() - self.root.winfo_rootx(),
                y=self.entry.winfo_rooty() - self.root.winfo_rooty() + self.entry.winfo_height(),
                width=self.entry.winfo_width()
            )

            for match in matches[:5]:
                name = os.path.splitext(match)[0]
                lbl = ctk.CTkLabel(self.suggestion_frame, text=name, anchor="w", cursor="hand2",
                                   font=("Arial", 12), text_color="#003366", fg_color="transparent")
                lbl.pack(fill="x", padx=5, pady=2)

                def on_click(e, fn=match):
                    self.entry.delete(0, "end")
                    self.entry.insert(0, name)
                    self.search()

                def on_enter(e, label=lbl):
                    label.configure(fg_color="#1f6aa5")  # CTk blue

                def on_leave(e, label=lbl):
                    label.configure(fg_color="transparent")

                lbl.bind("<Button-1>", on_click)
                lbl.bind("<Enter>", on_enter)
                lbl.bind("<Leave>", on_leave)
                self.suggestion_labels.append(lbl)

        def highlight_selection():
            for i, lbl in enumerate(self.suggestion_labels):
                if i == self.selected_index:
                    lbl.configure(fg_color="#1f6aa5")
                else:
                    lbl.configure(fg_color="transparent")

        def on_key(event):
            if event.keysym == "Down":
                if self.selected_index < len(self.suggestion_labels) - 1:
                    self.selected_index += 1
                    highlight_selection()
            elif event.keysym == "Up":
                if self.selected_index > 0:
                    self.selected_index -= 1
                    highlight_selection()
            elif event.keysym == "Return":
                if 0 <= self.selected_index < len(self.suggestion_labels):
                    selected_lbl = self.suggestion_labels[self.selected_index]
                    self.entry.delete(0, "end")
                    self.entry.insert(0, selected_lbl.cget("text"))
                    self.search()

        self.entry.bind("<KeyRelease>", update_suggestions)
        self.entry.bind("<KeyPress>", on_key)

    # ---------------- Display ----------------
    def _display_article_one_by_one(self, paragraphs, headings, html_content):
        last_nodes = {0: ""}
        self.toc_positions = []
        self.toc_widget_map = {}

        heading_map = {}
        for level, hid, htext in headings:
            level = int(level)
            clean_text = html.unescape(re.sub(r'<.*?>', '', htext)).strip()
            parent = last_nodes.get(level - 1, "")
            node = self.toc_tree.insert(parent, "end", text=clean_text)
            last_nodes[level] = node
            heading_map[clean_text.lower().strip()] = node

        html_content = re.sub(r'<li id="toc-mw-content-text".*?</li>', '', html_content, flags=re.DOTALL)
        content_blocks = re.split(r'(<h[1-6].*?>.*?</h[1-6]>|<p>.*?</p>)', html_content, flags=re.DOTALL)
        for block in content_blocks:
            block = block.strip()
            if not block:
                continue
            if block.startswith("<h"):
                match = re.match(r'<h([1-6]).*?>(.*?)</h[1-6]>', block, re.DOTALL)
                if match:
                    text = html.unescape(re.sub(r'<.*?>', '', match.group(2))).strip()
                    node = heading_map.get(text.lower().strip())
                    if node:
                        frame = ctk.CTkFrame(self.scrollable_frame, corner_radius=0, fg_color="transparent")
                        frame.pack(fill="x", pady=8)
                        lbl = ctk.CTkLabel(frame, text=text, font=("Arial", 14, "bold"),
                            anchor="w", wraplength=900, justify="left", fg_color="transparent")
                        lbl.pack(fill="x")
                        self.toc_positions.append(frame)
                        self.toc_widget_map[node] = frame
            elif block.startswith("<p>"):
                text = html.unescape(re.sub(r'<.*?>', '', block)).strip()
                if text:
                    frame = ctk.CTkFrame(self.scrollable_frame, corner_radius=0, fg_color="transparent")
                    frame.pack(fill="x", pady=4)
                    lbl = ctk.CTkLabel(frame, text=text, font=("Arial", 13),
                        anchor="w", wraplength=900, justify="left", fg_color="transparent")
                    lbl.pack(fill="x")

        self._add_images_in_batches(html_content)
        self._add_links(html_content, self.current_url)
        self._add_may_refer_to_links(html_content, self.current_url)
        self._add_references(html_content)
        self.stop_loading()
        self.canvas.yview_moveto(0)
        self._enable_mouse_scroll()

    def _animate_offline_badge(self):
        def pulse():
            colors = ["#666666", "#888888", "#aaaaaa", "#cccccc", "#aaaaaa", "#888888"]
            i = 0
            while True:
                self.offline_badge.configure(fg_color=colors[i % len(colors)])
                i += 1
                time.sleep(0.5)
        threading.Thread(target=pulse, daemon=True).start()

    def show_translator_panel(self):
        # Always clear and rebuild the translator panel
        self.entry.configure(state="disabled")
        self.clear_old()

        panel = ctk.CTkFrame(
            self.scrollable_frame,
            corner_radius=0,
            fg_color=self.scrollable_frame.cget("fg_color")
        )
        panel.pack(pady=40)

        ctk.CTkLabel(
            panel,
            text="Translator",
            font=("Arial", 16, "bold")
        ).pack(pady=10)

        lang_frame = ctk.CTkFrame(panel)
        lang_frame.pack(pady=5)

        languages = [
            "Detect Language", "English", "Spanish", "French", "German", "Chinese",
            "Arabic", "Russian", "Hindi", "Japanese", "Korean", "Turkish", "Portuguese",
            "Italian", "Dutch", "Polish", "Ukrainian", "Vietnamese", "Hebrew",
            "Indonesian", "Filipino", "Czech", "Greek", "Swedish", "Finnish",
            "Norwegian", "Danish", "Hungarian", "Romanian", "Thai", "Malay",
            "Slovak", "Bulgarian", "Serbian", "Croatian", "Persian", "Urdu",
            "Swahili", "Tamil", "Telugu", "Kannada"
        ]

        from_lang = ctk.CTkOptionMenu(lang_frame, values=languages)
        from_lang.set("Detect Language")
        from_lang.pack(side="left", padx=5)

        to_lang = ctk.CTkOptionMenu(lang_frame, values=languages)
        to_lang.set("English")
        to_lang.pack(side="left", padx=5)

        purple = "#6a5acd"
        from_lang.configure(fg_color=purple, button_color=purple, button_hover_color=purple)
        to_lang.configure(fg_color=purple, button_color=purple, button_hover_color=purple)

        text_input = ctk.CTkTextbox(panel, width=600, height=150)
        text_input.pack(pady=10)

        translate_btn = ctk.CTkButton(
            panel,
            text="Translate",
            command=lambda: self._real_translate(text_input, from_lang.get(), to_lang.get())
        )
        translate_btn.pack(pady=5)
        translate_btn.configure(fg_color=purple, hover_color=purple)

    def show_dictionary_panel(self):
        self.clear_old()
        self.entry.configure(state="normal")
        self.canvas.unbind_all("<MouseWheel>")
        self.scrollbar.pack_forget()

        panel = ctk.CTkFrame(self.scrollable_frame, corner_radius=0, fg_color=self.scrollable_frame.cget("fg_color"))
        panel.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(panel, text="Dictionary", font=("Arial", 16, "bold")).pack(pady=10)

        term = self.entry.get().strip()
        if not term:
            ctk.CTkLabel(panel, text="Search a word to find it's definition.", font=("Arial", 16, "bold")).pack(pady=10)
            return

        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{term}"
            response = requests.get(url, verify=False)
            data = response.json()

            if isinstance(data, dict) and data.get("title") == "No Definitions Found":
                ctk.CTkLabel(panel, text=f"No definition found for '{term}'.", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(pady=10)
            else:
                meanings = data[0].get("meanings", [])
                content = f"Definitions for '{term}':\n\n"
                for meaning in meanings:
                    pos = meaning.get("partOfSpeech", "")
                    for definition in meaning.get("definitions", []):
                        text = definition.get("definition", "")
                        example = definition.get("example", "")
                        content += f"• ({pos}) {text}\n"
                        if example:
                            content += f"    e.g. {example}\n"
                ctk.CTkLabel(panel, text=content.strip(), font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(fill="both", expand=True)
        except Exception as e:
            ctk.CTkLabel(panel, text=f"Error: {str(e)}", font=("Arial", 13), wraplength=900, justify="left", anchor="w").pack(fill="both", expand=True)

    def _lookup_definition(self, word, textbox):
        try:
            url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
            response = requests.get(url)
            data = response.json()

            if isinstance(data, dict) and data.get("title") == "No Definitions Found":
                textbox.delete("1.0", "end")
                textbox.insert("end", f"No definition found for '{word}'.")
                return

            meanings = data[0].get("meanings", [])
            output = f"Definitions for '{word}':\n\n"
            for meaning in meanings:
                part_of_speech = meaning.get("partOfSpeech", "")
                for definition in meaning.get("definitions", []):
                    text = definition.get("definition", "")
                    example = definition.get("example", "")
                    output += f"• ({part_of_speech}) {text}\n"
                    if example:
                        output += f"    e.g. {example}\n"
            textbox.delete("1.0", "end")
            textbox.insert("end", output.strip())
        except Exception as e:
            textbox.delete("1.0", "end")
            textbox.insert("end", f"Error: {str(e)}")

    # ---------------- Images ----------------
    def _add_images_in_batches(self, html_content):
        img_matches = re.findall(r'<img [^>]*(?:src|data-src)="([^"]+)"', html_content)
        img_frame = ctk.CTkFrame(self.scrollable_frame, corner_radius=0)
        img_frame.pack(pady=10, fill="x")
        shown = [0]

        def load_batch(start=0, batch_size=1):
            end = min(start + batch_size, len(img_matches))
            for i in range(start, end):
                img_url = unquote(img_matches[i])
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                elif img_url.startswith("/"):
                    img_url = urljoin("https://en.wikipedia.org", img_url)
                if any(x in img_url.lower() for x in ["svg","icon","wikimedia-button"]):
                    continue
                try:
                    local = os.path.join(IMG_FOLDER, f"img{shown[0]}.jpg")
                    with urlopen(Request(img_url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10) as r:
                        with open(local, "wb") as f:
                            f.write(r.read())

                    img_small = Image.open(local)
                    img_small.thumbnail((200, 150))
                    photo_small = ImageTk.PhotoImage(img_small)

                    lbl = ctk.CTkLabel(img_frame, image=photo_small, text="", cursor="hand2", corner_radius=0)
                    lbl.image = photo_small
                    lbl.local_path = local
                    lbl.pack(side="left", padx=5)

                    def show_overlay(event, path=local):
                        overlay = ctk.CTkFrame(self.root)
                        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

                        win_w = self.root.winfo_width()
                        win_h = self.root.winfo_height()

                        full_img = Image.open(path)
                        full_img.thumbnail((win_w, win_h), Image.LANCZOS)
                        photo_full = ImageTk.PhotoImage(full_img)

                        img_label = ctk.CTkLabel(overlay, image=photo_full, text="")
                        img_label.image = photo_full
                        img_label.pack(expand=True)

                        overlay.bind("<Button-1>", lambda e: overlay.destroy())
                        self.root.bind("<Escape>", lambda e: overlay.destroy())

                    lbl.bind("<Button-1>", show_overlay)

                    shown[0] += 1
                except Exception as e:
                    print("Image error:", e)
                    continue

            if end < len(img_matches):
                self.root.after(50, lambda: load_batch(end, batch_size))

        load_batch()

    # ---------------- Links ----------------
    def _add_links(self, html_content, base_url):
        links = re.findall(r'<a href="(/wiki/[^"#:]*)".*?>(.*?)</a>', html_content)
        if not links: return
        link_frame = ctk.CTkFrame(self.scrollable_frame)
        link_frame.pack(pady=10, fill="x")
        ctk.CTkLabel(link_frame, text="Related Articles:", font=("Arial",13,"bold")).pack(anchor="w")
        for href, text in links[:10]:
            clean_text = html.unescape(re.sub(r'<.*?>','',text))
            if not clean_text.strip(): continue
            btn = ctk.CTkButton(link_frame, text=clean_text, fg_color="transparent", hover_color="#ccc",
                                command=lambda u=urljoin("https://en.wikipedia.org", href): self.search(u))
            btn.pack(anchor="w")

    # ---------------- May Refer To ----------------
    def _add_may_refer_to_links(self, html_content, base_url):
        may_refer_match = re.search(r'(?:<p>.*?may refer to.*?</p>).*?(<ul>.*?</ul>)', html_content, re.DOTALL | re.IGNORECASE)
        if not may_refer_match:
            return
        ul_html = may_refer_match.group(1)
        links = re.findall(r'<li><a href="(/wiki/[^"#:]*)".*?>(.*?)</a>', ul_html)
        if not links:
            return

        ref_frame = ctk.CTkFrame(self.scrollable_frame)
        ref_frame.pack(pady=10, fill="x")
        ctk.CTkLabel(ref_frame, text="May Refer To:", font=("Arial",13,"bold")).pack(anchor="w")
        
        for href, text in links[:10]:
            clean_text = html.unescape(re.sub(r'<.*?>','',text))
            if not clean_text.strip(): continue
            btn = ctk.CTkButton(ref_frame, text=clean_text, fg_color="transparent", hover_color="#ccc",
                                command=lambda u=urljoin("https://en.wikipedia.org", href): self.search(u))
            btn.pack(anchor="w")

    # ---------------- References ----------------
    def _add_references(self, html_content):
        refs_match = re.search(r'(<ol class="references".*?</ol>)', html_content, re.DOTALL)
        if not refs_match:
            return
        refs_html = refs_match.group(1)
        ref_items = re.findall(r'<li[^>]*id="([^"]+)".*?>(.*?)</li>', refs_html, re.DOTALL)
        if not ref_items:
            return

        ref_frame = ctk.CTkFrame(self.scrollable_frame)
        ref_frame.pack(pady=10, fill="x")
        ctk.CTkLabel(ref_frame, text="References:", font=("Arial",13,"bold")).pack(anchor="w")
        for ref_id, ref_html in ref_items:
            clean_text = html.unescape(re.sub(r'<.*?>', '', ref_html).strip())
            if not clean_text:
                continue
            lbl = ctk.CTkLabel(ref_frame, text=f"[{ref_id}] {clean_text}", wraplength=900,
                               justify="left", anchor="w", font=("Arial", 11))
            lbl.pack(anchor="w", fill="x", pady=2)

    # ---------------- Error ----------------
    def _display_error(self, msg):
        self.stop_loading()
        self.clear_old()
        lbl = ctk.CTkLabel(self.scrollable_frame,
                           text=f"Article Not Found or No Internet.\n{msg}",
                           font=("Arial",14))
        lbl.pack(pady=20, anchor="center")
# ---------------- Run ----------------
if __name__ == "__main__":
    root = ctk.CTk()
    app = WikiBrowser(root)
    root.mainloop()
