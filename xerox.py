import sys
import os
import fitz  # PyMuPDF
from PIL import Image, ImageQt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGridLayout, QPushButton, QLabel, QFileDialog, QInputDialog, 
    QComboBox, QMessageBox, QLineEdit, QDialog, QRubberBand, QTabWidget, QSpinBox
)
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

# Standard Card Pixel Sizes (300 DPI)
CARD_W_PX = 1012  # 85.6 mm
CARD_H_PX = 638   # 53.98 mm

# Standard Photo Pixel Sizes (300 DPI)
PP_W_PX = 413     # 3.5 cm
PP_H_PX = 531     # 4.5 cm
STAMP_W_PX = 295  # 2.5 cm
STAMP_H_PX = 354  # 3.0 cm

# --- CROP DIALOG ---
class CropDialog(QDialog):
    def __init__(self, pil_image, side_title="Front"):
        super().__init__()
        self.setWindowTitle(f"Crop {side_title} (Drag mouse to select area)")
        self.resize(900, 650)
        self.setStyleSheet("background-color: #1a1a24; color: white;")
        
        self.pil_image = pil_image
        self.cropped_image = None
        self.origin = QPoint()
        
        layout = QVBoxLayout(self)
        header_lbl = QLabel(f"<b>Select {side_title} Area:</b> Drag a box over the desired portion and click 'Done Crop'")
        header_lbl.setStyleSheet("color: #4dabf7; font-size: 14px; margin-bottom: 5px;")
        layout.addWidget(header_lbl)
        
        self.img_lbl = QLabel(self)
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        q_img = ImageQt.ImageQt(pil_image)
        self.display_pixmap = QPixmap.fromImage(q_img).scaled(850, 520, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.img_lbl.setPixmap(self.display_pixmap)
        layout.addWidget(self.img_lbl)
        
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self.img_lbl)
        
        btn_box = QHBoxLayout()
        btn_done = QPushButton("✅ Done Crop")
        btn_done.setStyleSheet("padding: 10px; background-color: #198754; font-weight: bold; border-radius: 4px;")
        btn_done.clicked.connect(self.apply_crop)
        
        btn_cancel = QPushButton("❌ Cancel")
        btn_cancel.setStyleSheet("padding: 10px; background-color: #dc3545; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_done)
        layout.addLayout(btn_box)
        
        self.img_lbl.mousePressEvent = self.mouse_press
        self.img_lbl.mouseMoveEvent = self.mouse_move

    def mouse_press(self, event):
        self.origin = event.pos()
        self.rubberBand.setGeometry(QRect(self.origin, QSize()))
        self.rubberBand.show()

    def mouse_move(self, event):
        self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def apply_crop(self):
        rect = self.rubberBand.geometry()
        if rect.width() < 20 or rect.height() < 20:
            QMessageBox.warning(self, "Invalid Selection", "Please drag a valid area first!")
            return
            
        disp_w = self.display_pixmap.width()
        disp_h = self.display_pixmap.height()
        lbl_w = self.img_lbl.width()
        lbl_h = self.img_lbl.height()
        
        offset_x = (lbl_w - disp_w) // 2
        offset_y = (lbl_h - disp_h) // 2
        
        rel_x = max(0, rect.x() - offset_x)
        rel_y = max(0, rect.y() - offset_y)
        rel_w = min(rect.width(), disp_w - rel_x)
        rel_h = min(rect.height(), disp_h - rel_y)
        
        orig_w, orig_h = self.pil_image.size
        scale_x = orig_w / disp_w
        scale_y = orig_h / disp_h
        
        crop_box = (
            int(rel_x * scale_x),
            int(rel_y * scale_y),
            int((rel_x + rel_w) * scale_x),
            int((rel_y + rel_h) * scale_y)
        )
        
        self.cropped_image = self.pil_image.crop(crop_box)
        self.accept()

# --- MAIN WINDOW WITH 2 TABS ---
class UltimatePrintStudio(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart PVC & Passport Photo Studio (Offline Suite)")
        self.resize(1150, 780)
        self.setStyleSheet("background-color: #1e1e24; color: #ffffff;")
        
        self.card_slots = [None] * 5
        self.passport_img = None
        self.photo_copies = 8
        
        self.init_ui()

    def init_ui(self):
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #444; background: #1e1e24; }
            QTabBar::tab { background: #2b2b36; color: white; padding: 12px 25px; font-weight: bold; font-size: 14px; }
            QTabBar::tab:selected { background: #0d6efd; }
        """)

        # TAB 1: PVC CARD STUDIO
        tab_pvc = QWidget()
        pvc_layout = QHBoxLayout(tab_pvc)
        
        sidebar_pvc = QVBoxLayout()
        sidebar_pvc.addWidget(QLabel("<b>DOCUMENT TYPE:</b>"))
        self.doc_type = QComboBox()
        self.doc_type.addItems([
            "Aadhaar (Standard Auto)",
            "e-PAN (NSDL Auto)",
            "e-PAN (UTI Auto)",
            "✂️ Manual Custom Crop",
            "Voter ID / Other Card"
        ])
        self.doc_type.setStyleSheet("padding: 8px; background-color: #2b2b36; border: 1px solid #444; border-radius: 4px;")
        sidebar_pvc.addWidget(self.doc_type)

        btn_load_pvc = QPushButton("📂 Load Card Doc")
        btn_load_pvc.setStyleSheet("padding: 10px; background-color: #0d6efd; font-weight: bold; border-radius: 4px;")
        btn_load_pvc.clicked.connect(self.load_pvc_doc)
        sidebar_pvc.addWidget(btn_load_pvc)

        sidebar_pvc.addSpacing(15)
        btn_print_pvc = QPushButton("🖨️ Print PVC (A4 / Tray)")
        btn_print_pvc.setStyleSheet("padding: 12px; background-color: #198754; font-weight: bold; font-size: 14px; border-radius: 4px;")
        btn_print_pvc.clicked.connect(self.print_pvc)
        sidebar_pvc.addWidget(btn_print_pvc)

        btn_clear_pvc = QPushButton("🗑️ Clear PVC Slots")
        btn_clear_pvc.setStyleSheet("padding: 8px; background-color: #dc3545; border-radius: 4px;")
        btn_clear_pvc.clicked.connect(self.clear_pvc)
        sidebar_pvc.addWidget(btn_clear_pvc)
        sidebar_pvc.addStretch()

        pvc_layout.addLayout(sidebar_pvc, 1)

        grid_container = QWidget()
        self.grid = QGridLayout(grid_container)
        self.f_labels = []
        self.b_labels = []

        for i in range(5):
            f_lbl = QLabel(f"Front {i+1}\n(Empty)")
            f_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            f_lbl.setStyleSheet("border: 2px dashed #555; background-color: #2b2b36; border-radius: 6px;")
            f_lbl.setFixedSize(200, 126)
            self.f_labels.append(f_lbl)
            self.grid.addWidget(f_lbl, i, 0)

            b_lbl = QLabel(f"Back {i+1}\n(Empty)")
            b_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            b_lbl.setStyleSheet("border: 2px dashed #555; background-color: #2b2b36; border-radius: 6px;")
            b_lbl.setFixedSize(200, 126)
            self.b_labels.append(b_lbl)
            self.grid.addWidget(b_lbl, i, 1)

        pvc_layout.addWidget(grid_container, 4)
        tabs.addTab(tab_pvc, "💳 PVC Card Studio")

        # TAB 2: PASSPORT PHOTO STUDIO
        tab_photo = QWidget()
        photo_layout = QHBoxLayout(tab_photo)

        sidebar_photo = QVBoxLayout()
        sidebar_photo.addWidget(QLabel("<b>PHOTO PRESET:</b>"))
        self.photo_type = QComboBox()
        self.photo_type.addItems([
            "Passport Size (3.5 x 4.5 cm)",
            "Stamp Size (2.5 x 3.0 cm)"
        ])
        self.photo_type.setStyleSheet("padding: 8px; background-color: #2b2b36; border: 1px solid #444; border-radius: 4px;")
        sidebar_photo.addWidget(self.photo_type)

        sidebar_photo.addWidget(QLabel("<b>SHEET COPIES:</b>"))
        self.copies_box = QComboBox()
        self.copies_box.addItems(["8 Photos (4x6 Sheet)", "4 Photos (4x6 Sheet)", "16 Photos (A4 Sheet)"])
        self.copies_box.setStyleSheet("padding: 8px; background-color: #2b2b36; border: 1px solid #444; border-radius: 4px;")
        self.copies_box.currentIndexChanged.connect(self.update_photo_preview)
        sidebar_photo.addWidget(self.copies_box)

        btn_load_photo = QPushButton("📷 Load & Crop Photo")
        btn_load_photo.setStyleSheet("padding: 10px; background-color: #0d6efd; font-weight: bold; border-radius: 4px;")
        btn_load_photo.clicked.connect(self.load_and_crop_photo)
        sidebar_photo.addWidget(btn_load_photo)

        sidebar_photo.addSpacing(15)
        btn_print_photo = QPushButton("🖨️ Print Photo Sheet")
        btn_print_photo.setStyleSheet("padding: 12px; background-color: #198754; font-weight: bold; font-size: 14px; border-radius: 4px;")
        btn_print_photo.clicked.connect(self.print_photo_sheet)
        sidebar_photo.addWidget(btn_print_photo)

        btn_clear_photo = QPushButton("🗑️ Clear Photo")
        btn_clear_photo.setStyleSheet("padding: 8px; background-color: #dc3545; border-radius: 4px;")
        btn_clear_photo.clicked.connect(self.clear_photo)
        sidebar_photo.addWidget(btn_clear_photo)
        sidebar_photo.addStretch()

        photo_layout.addLayout(sidebar_photo, 1)

        # Photo Sheet Preview Box
        self.sheet_preview = QLabel("Upload & Crop a Photo to view Sheet Preview")
        self.sheet_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sheet_preview.setStyleSheet("border: 2px dashed #555; background-color: #2b2b36; border-radius: 8px; font-size: 15px; color: #888;")
        photo_layout.addWidget(self.sheet_preview, 4)

        tabs.addTab(tab_photo, "📸 Passport / Stamp Photo Studio")

        self.setCentralWidget(tabs)

    # --- PVC FUNCTIONS ---
    def load_pvc_doc(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Card Document", "", "Documents (*.pdf *.png *.jpg *.jpeg)")
        if not file_path:
            return

        slot_idx = -1
        for idx, val in enumerate(self.card_slots):
            if val is None:
                slot_idx = idx
                break

        if slot_idx == -1:
            QMessageBox.warning(self, "Slots Full", "All 5 slots full! Clear or print first.")
            return

        try:
            selected_doc = self.doc_type.currentText()
            if file_path.lower().endswith(".pdf"):
                doc = fitz.open(file_path)
                if doc.is_encrypted:
                    pwd, ok = QInputDialog.getText(self, "PDF Password", "Enter Aadhaar Password:", QLineEdit.EchoMode.Password)
                    if ok and pwd:
                        if not doc.authenticate(pwd):
                            QMessageBox.critical(self, "Error", "Incorrect Password!")
                            return
                    else:
                        return
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                full_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                doc.close()
            else:
                full_img = Image.open(file_path).convert("RGB")

            w, h = full_img.size

            if "Manual" in selected_doc or "Other" in selected_doc:
                dlg_f = CropDialog(full_img, "FRONT")
                if dlg_f.exec() == QDialog.DialogCode.Accepted:
                    front_img = dlg_f.cropped_image.resize((CARD_W_PX, CARD_H_PX), Image.Resampling.LANCZOS)
                else:
                    return

                dlg_b = CropDialog(full_img, "BACK")
                if dlg_b.exec() == QDialog.DialogCode.Accepted:
                    back_img = dlg_b.cropped_image.resize((CARD_W_PX, CARD_H_PX), Image.Resampling.LANCZOS)
                else:
                    return
            else:
                if "Aadhaar" in selected_doc:
                    front_box = (int(w * 0.05), int(h * 0.705), int(w * 0.495), int(h * 0.985))
                    back_box = (int(w * 0.505), int(h * 0.705), int(w * 0.950), int(h * 0.985))
                elif "PAN" in selected_doc:
                    front_box = (int(w * 0.05), int(h * 0.40), int(w * 0.49), int(h * 0.75))
                    back_box = (int(w * 0.51), int(h * 0.40), int(w * 0.95), int(h * 0.75))
                else:
                    front_box = (0, 0, int(w * 0.5), h)
                    back_box = (int(w * 0.5), 0, w, h)

                front_img = full_img.crop(front_box).resize((CARD_W_PX, CARD_H_PX), Image.Resampling.LANCZOS)
                back_img = full_img.crop(back_box).resize((CARD_W_PX, CARD_H_PX), Image.Resampling.LANCZOS)

            self.card_slots[slot_idx] = (front_img, back_img)
            q_f = ImageQt.ImageQt(front_img)
            q_b = ImageQt.ImageQt(back_img)
            self.f_labels[slot_idx].setPixmap(QPixmap.fromImage(q_f).scaled(200, 126, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.b_labels[slot_idx].setPixmap(QPixmap.fromImage(q_b).scaled(200, 126, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed: {str(e)}")

    def print_pvc(self):
        if not any(self.card_slots):
            QMessageBox.information(self, "Empty", "No cards loaded!")
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            page_rect = printer.pageRect(QPrinter.Unit.Millimeter)
            card_w_mm, card_h_mm = 85.6, 53.98
            margin_left_mm, gap_x_mm = 12.0, 14.0
            margin_top_mm, gap_y_mm = 10.0, 4.0

            scale_x = printer.width() / page_rect.width()
            scale_y = printer.height() / page_rect.height()

            for i, card in enumerate(self.card_slots):
                if card is not None:
                    front_pil, back_pil = card
                    q_front = ImageQt.ImageQt(front_pil)
                    q_back = ImageQt.ImageQt(back_pil)

                    f_x = int(margin_left_mm * scale_x)
                    f_y = int((margin_top_mm + i * (card_h_mm + gap_y_mm)) * scale_y)
                    b_x = int((margin_left_mm + card_w_mm + gap_x_mm) * scale_x)
                    b_y = f_y

                    draw_w = int(card_w_mm * scale_x)
                    draw_h = int(card_h_mm * scale_y)

                    painter.drawImage(f_x, f_y, q_front.scaled(draw_w, draw_h, Qt.AspectRatioMode.IgnoreAspectRatio))
                    painter.drawImage(b_x, b_y, q_back.scaled(draw_w, draw_h, Qt.AspectRatioMode.IgnoreAspectRatio))

            painter.end()
            QMessageBox.information(self, "Sent", "PVC Print sent to printer!")

    def clear_pvc(self):
        self.card_slots = [None] * 5
        for i in range(5):
            self.f_labels[i].clear()
            self.f_labels[i].setText(f"Front {i+1}\n(Empty)")
            self.b_labels[i].clear()
            self.b_labels[i].setText(f"Back {i+1}\n(Empty)")

    # --- PASSPORT PHOTO FUNCTIONS ---
    def load_and_crop_photo(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Customer Photo", "", "Images (*.jpg *.png *.jpeg)")
        if not file_path:
            return
        
        orig_img = Image.open(file_path).convert("RGB")
        dlg = CropDialog(orig_img, "PASSPORT PHOTO")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            crop_target = (PP_W_PX, PP_H_PX) if "Passport" in self.photo_type.currentText() else (STAMP_W_PX, STAMP_H_PX)
            self.passport_img = dlg.cropped_image.resize(crop_target, Image.Resampling.LANCZOS)
            self.update_photo_preview()

    def update_photo_preview(self):
        if self.passport_img is None:
            return

        choice = self.copies_box.currentText()
        if "8 Photos" in choice:
            cols, rows = 4, 2
        elif "4 Photos" in choice:
            cols, rows = 2, 2
        else: # 16 Photos
            cols, rows = 4, 4

        # Create Preview Canvas
        pw, ph = self.passport_img.size
        sheet_w = (pw + 30) * cols + 40
        sheet_h = (ph + 30) * rows + 40
        sheet_img = Image.new("RGB", (sheet_w, sheet_h), (255, 255, 255))

        for r in range(rows):
            for c in range(cols):
                x = 40 + c * (pw + 30)
                y = 40 + r * (ph + 30)
                sheet_img.paste(self.passport_img, (x, y))

        q_sheet = ImageQt.ImageQt(sheet_img)
        pm = QPixmap.fromImage(q_sheet).scaled(650, 480, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.sheet_preview.setPixmap(pm)

    def print_photo_sheet(self):
        if self.passport_img is None:
            QMessageBox.information(self, "Empty", "No photo cropped!")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        print_dialog = QPrintDialog(printer, self)
        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:
            painter = QPainter(printer)
            page_rect = printer.pageRect(QPrinter.Unit.Millimeter)

            choice = self.copies_box.currentText()
            cols, rows = (4, 2) if "8 Photos" in choice else ((2, 2) if "4 Photos" in choice else (4, 4))

            p_w_mm = 35.0 if "Passport" in self.photo_type.currentText() else 25.0
            p_h_mm = 45.0 if "Passport" in self.photo_type.currentText() else 30.0

            scale_x = printer.width() / page_rect.width()
            scale_y = printer.height() / page_rect.height()

            margin_x = 10.0
            margin_y = 10.0
            gap = 3.0

            q_p = ImageQt.ImageQt(self.passport_img)
            draw_w = int(p_w_mm * scale_x)
            draw_h = int(p_h_mm * scale_y)

            for r in range(rows):
                for c in range(cols):
                    pos_x = int((margin_x + c * (p_w_mm + gap)) * scale_x)
                    pos_y = int((margin_y + r * (p_h_mm + gap)) * scale_y)
                    painter.drawImage(pos_x, pos_y, q_p.scaled(draw_w, draw_h, Qt.AspectRatioMode.IgnoreAspectRatio))

            painter.end()
            QMessageBox.information(self, "Sent", "Photo sheet sent to printer!")

    def clear_photo(self):
        self.passport_img = None
        self.sheet_preview.clear()
        self.sheet_preview.setText("Upload & Crop a Photo to view Sheet Preview")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UltimatePrintStudio()
    window.show()
    sys.exit(app.exec())