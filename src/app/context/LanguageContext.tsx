/**
 * LanguageContext.tsx — Internationalization context for FinLedger AI.
 * Supports English (en), Hindi (hi), Gujarati (gu), Tamil (ta), and Marathi (mr).
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";

export type SupportedLanguage = "en" | "hi" | "gu" | "ta" | "mr";

export interface LanguageContextType {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  t: (key: string) => string;
}

const translations: Record<SupportedLanguage, Record<string, string>> = {
  en: {
    // Nav
    "nav.menu": "Menu",
    "nav.dashboard": "Dashboard",
    "nav.workspace": "Workspace",
    "nav.assistant": "AI Assistant",
    "nav.updates": "Government Updates",
    "nav.reports": "Reports",
    "nav.settings": "Settings",
    "nav.pro_plan": "Pro plan",
    "nav.pro_desc": "Unlimited AI audits & OCR",
    "nav.manage_plan": "Manage plan",
    "header.search": "Search clients, invoices, reports...",
    "header.role": "Chartered Accountant",
    "header.sign_out": "Sign out",

    // Settings
    "settings.title": "Settings",
    "settings.subtitle": "Manage your profile, security and preferences",
    "settings.tabs.profile": "Profile",
    "settings.tabs.security": "Security",
    "settings.tabs.notifications": "Notifications",
    "settings.tabs.preferences": "Preferences",

    // Profile Tab
    "profile.card_title": "Profile",
    "profile.card_desc": "Update your personal information",
    "profile.change_photo": "Change photo",
    "profile.remove_photo": "Remove",
    "profile.photo_helper": "JPG or PNG, max 2 MB",
    "profile.first_name": "First name",
    "profile.last_name": "Last name",
    "profile.email": "Email",
    "profile.membership_no": "Membership No.",
    "profile.save_changes": "Save changes",
    "profile.saving": "Saving...",

    // Security Tab
    "security.card_title": "Security",
    "security.two_factor": "Two-factor authentication",
    "security.two_factor_desc": "Add an extra layer of security",
    "security.login_alerts": "Login alerts",
    "security.login_alerts_desc": "Get notified of new sign-ins",
    "security.session_timeout": "Session timeout",
    "security.session_timeout_desc": "Auto sign-out after inactivity",
    "security.change_password": "Change password",
    "security.change_password_desc": "Enter your current password and choose a new secure password.",
    "security.current_password": "Current password",
    "security.new_password": "New password",
    "security.confirm_password": "Confirm new password",
    "security.cancel": "Cancel",
    "security.update_password": "Update password",
    "security.updating": "Updating...",
    "security.min_chars": "At least 6 characters",
    "security.enter_current": "Enter current password",
    "security.reenter_new": "Re-enter new password",
    "security.password_mismatch": "Passwords do not match",

    // Notifications Tab
    "notifications.card_title": "Notification Preferences",
    "notifications.compliance": "Compliance deadlines",
    "notifications.compliance_desc": "GST & tax filing reminders",
    "notifications.audit": "Audit alerts",
    "notifications.audit_desc": "Fraud & risk notifications",
    "notifications.client": "Client activity",
    "notifications.client_desc": "Uploads & status changes",
    "notifications.product": "Product updates",
    "notifications.product_desc": "New features & tips",

    // Preferences Tab
    "preferences.card_title": "Preferences",
    "preferences.language": "Language",
    "preferences.language_desc": "Interface language",
    "preferences.currency": "Currency",
    "preferences.currency_desc": "Default currency for Indian taxation & compliance",
    "preferences.currency_locked_desc": "Only Indian Rupee (INR ₹) is used for Indian CA operations",
    "preferences.theme": "Theme",
    "preferences.theme_desc": "Appearance",
    "preferences.theme_dark": "Dark",
    "preferences.theme_light": "Light",
  },

  hi: {
    // Nav
    "nav.menu": "मेनू",
    "nav.dashboard": "डैशबोर्ड",
    "nav.workspace": "कार्यक्षेत्र",
    "nav.assistant": "एआई सहायक",
    "nav.updates": "सरकारी नियम व अपडेट्स",
    "nav.reports": "वित्तीय रिपोर्ट",
    "nav.settings": "सेटिंग्स",
    "nav.pro_plan": "प्रो प्लान",
    "nav.pro_desc": "असीमित एआई ऑडिट और ओसीआर",
    "nav.manage_plan": "प्लान प्रबंधित करें",
    "header.search": "क्लाइंट, इनवॉइस, रिपोर्ट खोजें...",
    "header.role": "सनदी लेखाकार (CA)",
    "header.sign_out": "लॉग आउट",

    // Settings
    "settings.title": "सेटिंग्स",
    "settings.subtitle": "अपनी प्रोफ़ाइल, सुरक्षा और प्राथमिकताएं प्रबंधित करें",
    "settings.tabs.profile": "प्रोफ़ाइल",
    "settings.tabs.security": "सुरक्षा",
    "settings.tabs.notifications": "सूचनाएं",
    "settings.tabs.preferences": "प्राथमिकताएं",

    // Profile Tab
    "profile.card_title": "व्यक्तिगत प्रोफ़ाइल",
    "profile.card_desc": "अपनी व्यक्तिगत जानकारी अपडेट करें",
    "profile.change_photo": "फ़ोटो बदलें",
    "profile.remove_photo": "हटाएं",
    "profile.photo_helper": "JPG या PNG, अधिकतम 2 MB",
    "profile.first_name": "पहला नाम",
    "profile.last_name": "अंतिम नाम",
    "profile.email": "ईमेल",
    "profile.membership_no": "सदस्यता संख्या (ICAI)",
    "profile.save_changes": "बदलाव सहेजें",
    "profile.saving": "सहेजा जा रहा है...",

    // Security Tab
    "security.card_title": "सुरक्षा सेटिंग्स",
    "security.two_factor": "दो-चरणीय प्रमाणीकरण (2FA)",
    "security.two_factor_desc": "अपने खाते में अतिरिक्त सुरक्षा जोड़ें",
    "security.login_alerts": "लॉगिन अलर्ट",
    "security.login_alerts_desc": "नए साइन-इन की तत्काल सूचना प्राप्त करें",
    "security.session_timeout": "सत्र समाप्ति समय",
    "security.session_timeout_desc": "निष्क्रियता के बाद स्वतः साइन-आउट",
    "security.change_password": "पासवर्ड बदलें",
    "security.change_password_desc": "अपना वर्तमान पासवर्ड दर्ज करें और एक नया सुरक्षित पासवर्ड चुनें।",
    "security.current_password": "वर्तमान पासवर्ड",
    "security.new_password": "नया पासवर्ड",
    "security.confirm_password": "नए पासवर्ड की पुष्टि करें",
    "security.cancel": "रद्द करें",
    "security.update_password": "पासवर्ड अपडेट करें",
    "security.updating": "अपडेट हो रहा है...",
    "security.min_chars": "कम से कम 6 अक्षर",
    "security.enter_current": "वर्तमान पासवर्ड दर्ज करें",
    "security.reenter_new": "नया पासवर्ड पुनः दर्ज करें",
    "security.password_mismatch": "पासवर्ड मेल नहीं खा रहे हैं",

    // Notifications Tab
    "notifications.card_title": "सूचना प्राथमिकताएं",
    "notifications.compliance": "अनुपालन समयसीमा",
    "notifications.compliance_desc": "जीएसटी और आयकर रिटर्न फाइलिंग अनुस्मारक",
    "notifications.audit": "ऑडिट अलर्ट",
    "notifications.audit_desc": "विसंगति, धोखाधड़ी और जोखिम सूचनाएं",
    "notifications.client": "क्लाइंट गतिविधि",
    "notifications.client_desc": "दस्तावेज़ अपलोड और स्थिति परिवर्तन",
    "notifications.product": "उत्पाद अपडेट्स",
    "notifications.product_desc": "नई सुविधाएं और महत्वपूर्ण सुझाव",

    // Preferences Tab
    "preferences.card_title": "इंटरफ़ेस प्राथमिकताएं",
    "preferences.language": "भाषा",
    "preferences.language_desc": "एप्लिकेशन भाषा",
    "preferences.currency": "मुद्रा",
    "preferences.currency_desc": "भारतीय कराधान और अनुपालन के लिए मानक मुद्रा",
    "preferences.currency_locked_desc": "भारतीय सीए कार्यों के लिए केवल भारतीय रुपया (INR ₹) मान्य है",
    "preferences.theme": "थीम",
    "preferences.theme_desc": "रंग रूप (Appearance)",
    "preferences.theme_dark": "डार्क",
    "preferences.theme_light": "लाइट",
  },

  gu: {
    // Nav
    "nav.menu": "મેનૂ",
    "nav.dashboard": "ડેશબોર્ડ",
    "nav.workspace": "કાર્યક્ષેત્ર",
    "nav.assistant": "AI સહાયક",
    "nav.updates": "સરકારી અપડેટ્સ",
    "nav.reports": "અહેવાલો",
    "nav.settings": "સેટિંગ્સ",
    "nav.pro_plan": "પ્રો પ્લાન",
    "nav.pro_desc": "અમર્યાદિત AI ઓડિટ અને OCR",
    "nav.manage_plan": "પ્લાન મેનેજ કરો",
    "header.search": "ગ્રાહકો, ઇન્વૉઇસેસ, અહેવાલો શોધો...",
    "header.role": "ચાર્ટર્ડ એકાઉન્ટન્ટ (CA)",
    "header.sign_out": "સાઇન આઉટ",

    // Settings
    "settings.title": "સેટિંગ્સ",
    "settings.subtitle": "તમારી પ્રોફાઇલ, સુરક્ષા અને પસંદગીઓનું સંચાલન કરો",
    "settings.tabs.profile": "પ્રોફાઇલ",
    "settings.tabs.security": "સુરક્ષા",
    "settings.tabs.notifications": "સૂચનાઓ",
    "settings.tabs.preferences": "પસંદગીઓ",

    // Profile Tab
    "profile.card_title": "પ્રોફાઇલ",
    "profile.card_desc": "તમારી વ્યક્તિગત માહિતી અપડેટ કરો",
    "profile.change_photo": "ફોટો બદલો",
    "profile.remove_photo": "દૂર કરો",
    "profile.photo_helper": "JPG અથવા PNG, મહત્તમ 2 MB",
    "profile.first_name": "પ્રથમ નામ",
    "profile.last_name": "છેલ્લું નામ",
    "profile.email": "ઇમેઇલ",
    "profile.membership_no": "સદસ્યતા નંબર (ICAI)",
    "profile.save_changes": "ફેરફારો સાચવો",
    "profile.saving": "સાચવી રહ્યું છે...",

    // Security Tab
    "security.card_title": "સુરક્ષા",
    "security.two_factor": "દ્વિ-પરિબળ પ્રમાણીકરણ",
    "security.two_factor_desc": "વધારાની સુરક્ષા ઉમેરો",
    "security.login_alerts": "લૉગિન ચેતવણીઓ",
    "security.login_alerts_desc": "નવા સાઇન-ઇન વિશે સૂચિત થાઓ",
    "security.session_timeout": "સત્ર સમાપ્તિ",
    "security.session_timeout_desc": "નિષ્ક્રિયતા પછી આપમેળે સાઇન-આઉટ",
    "security.change_password": "પાસવર્ડ બદલો",
    "security.change_password_desc": "તમારો વર્તમાન પાસવર્ડ દાખલ કરો અને નવો પાસવર્ડ પસંદ કરો.",
    "security.current_password": "વર્તમાન પાસવર્ડ",
    "security.new_password": "નવો પાસવર્ડ",
    "security.confirm_password": "નવા પાસવર્ડની પુષ્ટિ કરો",
    "security.cancel": "રદ કરો",
    "security.update_password": "પાસવર્ડ અપડેટ કરો",
    "security.updating": "અપડેટ થઈ રહ્યું છે...",
    "security.min_chars": "ઓછામાં ઓછા 6 અક્ષરો",
    "security.enter_current": "વર્તમાન પાસવર્ડ દાખલ કરો",
    "security.reenter_new": "નવો પાસવર્ડ ફરીથી દાખલ કરો",
    "security.password_mismatch": "પાસવર્ડ મેળ ખાતા નથી",

    // Notifications Tab
    "notifications.card_title": "સૂચના પસંદગીઓ",
    "notifications.compliance": "અનુપાલન સમયમર્યાદા",
    "notifications.compliance_desc": "GST અને ટેક્સ ફાઇલિંગ રિમાઇન્ડર્સ",
    "notifications.audit": "ઓડિટ ચેતવણીઓ",
    "notifications.audit_desc": "જોખમ અને છેતરપિંડી સૂચનાઓ",
    "notifications.client": "ગ્રાહક પ્રવૃત્તિ",
    "notifications.client_desc": "અપલોડ્સ અને સ્થિતિ ફેરફારો",
    "notifications.product": "ઉત્પાદન અપડેટ્સ",
    "notifications.product_desc": "નવી સુવિધાઓ અને ટીપ્સ",

    // Preferences Tab
    "preferences.card_title": "પસંદગીઓ",
    "preferences.language": "ભાષા",
    "preferences.language_desc": "ઇન્ટરફેસ ભાષા",
    "preferences.currency": "ચલણ",
    "preferences.currency_desc": "ભારતીય કરવેરા માટે ડિફોલ્ટ ચલણ",
    "preferences.currency_locked_desc": "માત્ર ભારતીય રૂપિયો (INR ₹) સમર્થિત છે",
    "preferences.theme": "થીમ",
    "preferences.theme_desc": "દેખાવ",
    "preferences.theme_dark": "ડાર્ક",
    "preferences.theme_light": "લાઇટ",
  },

  mr: {
    // Nav
    "nav.menu": "मेनू",
    "nav.dashboard": "डॅशबोर्ड",
    "nav.workspace": "कार्यक्षेत्र",
    "nav.assistant": "AI सहाय्यक",
    "nav.updates": "सरकारी नियम व अपडेट्स",
    "nav.reports": "अहवाल",
    "nav.settings": "सेटिंग्ज",
    "nav.pro_plan": "प्रो प्लॅन",
    "nav.pro_desc": "अमर्यादित AI ऑडिट आणि OCR",
    "nav.manage_plan": "प्लॅन व्यवस्थापित करा",
    "header.search": "ग्राहक, पावत्या, अहवाल शोधा...",
    "header.role": "सनदी लेखापाल (CA)",
    "header.sign_out": "साइन आउट",

    // Settings
    "settings.title": "सेटिंग्ज",
    "settings.subtitle": "आपले प्रोफाइल, सुरक्षा आणि प्राधान्ये व्यवस्थापित करा",
    "settings.tabs.profile": "प्रोफाइल",
    "settings.tabs.security": "सुरक्षा",
    "settings.tabs.notifications": "सूचना",
    "settings.tabs.preferences": "प्राधान्ये",

    // Profile Tab
    "profile.card_title": "प्रोफाइल",
    "profile.card_desc": "आपली वैयक्तिक माहिती अपडेट करा",
    "profile.change_photo": "फोटो बदला",
    "profile.remove_photo": "काढून टाका",
    "profile.photo_helper": "JPG किंवा PNG, कमाल 2 MB",
    "profile.first_name": "पहिले नाव",
    "profile.last_name": "आडनाव",
    "profile.email": "ईमेल",
    "profile.membership_no": "सदस्यता क्रमांक (ICAI)",
    "profile.save_changes": "बदल जतन करा",
    "profile.saving": "जतन करत आहे...",

    // Security Tab
    "security.card_title": "सुरक्षा",
    "security.two_factor": "द्वि-घटक प्रमाणीकरण",
    "security.two_factor_desc": "अतिरिक्त सुरक्षा स्तर जोडा",
    "security.login_alerts": "लॉगिन सूचना",
    "security.login_alerts_desc": "नवीन साइन-इनच्या सूचना मिळवा",
    "security.session_timeout": "सत्र समाप्ती",
    "security.session_timeout_desc": "निष्क्रियतेनंतर स्वयंचलित साइन-आउट",
    "security.change_password": "पासवर्ड बदला",
    "security.change_password_desc": "आपला वर्तमान पासवर्ड प्रविष्ट करा आणि नवीन पासवर्ड निवडा.",
    "security.current_password": "वर्तमान पासवर्ड",
    "security.new_password": "नवीन पासवर्ड",
    "security.confirm_password": "नवीन पासवर्डची पुष्टी करा",
    "security.cancel": "रद्द करा",
    "security.update_password": "पासवर्ड अपडेट करा",
    "security.updating": "अपडेट होत आहे...",
    "security.min_chars": "किमान 6 वर्ण",
    "security.enter_current": "वर्तमान पासवर्ड प्रविष्ट करा",
    "security.reenter_new": "नवीन पासवर्ड पुन्हा प्रविष्ट करा",
    "security.password_mismatch": "पासवर्ड जुळत नाहीत",

    // Notifications Tab
    "notifications.card_title": "सूचना प्राधान्ये",
    "notifications.compliance": "अनुपालन मुदत",
    "notifications.compliance_desc": "GST आणि कर रिटर्न स्मरणपत्रे",
    "notifications.audit": "ऑडिट सूचना",
    "notifications.audit_desc": "जोखीम व विसंगती सूचना",
    "notifications.client": "ग्राहक क्रियाकलाप",
    "notifications.client_desc": "अपलोड आणि स्थितीतील बदल",
    "notifications.product": "उत्पादन अपडेट्स",
    "notifications.product_desc": "नवीन वैशिष्ट्ये आणि टिपा",

    // Preferences Tab
    "preferences.card_title": "प्राधान्ये",
    "preferences.language": "भाषा",
    "preferences.language_desc": "इंटरफेस भाषा",
    "preferences.currency": "चलन",
    "preferences.currency_desc": "भारतीय कर आकारणीसाठी डीफॉल्ट चलन",
    "preferences.currency_locked_desc": "केवळ भारतीय रुपया (INR ₹) समर्थित आहे",
    "preferences.theme": "थीम",
    "preferences.theme_desc": "दिसणे (Appearance)",
    "preferences.theme_dark": "डार्क",
    "preferences.theme_light": "लाइट",
  },

  ta: {
    // Nav
    "nav.menu": "மெனு",
    "nav.dashboard": "டாஷ்போர்டு",
    "nav.workspace": "பணியிடம்",
    "nav.assistant": "AI உதவியாளர்",
    "nav.updates": "அரசு அறிவிப்புகள்",
    "nav.reports": "அறிக்கைகள்",
    "nav.settings": "அமைப்புகள்",
    "nav.pro_plan": "ப்ரோ திட்டம்",
    "nav.pro_desc": "வரம்பற்ற AI தணிக்கைகள் & OCR",
    "nav.manage_plan": "திட்டத்தை நிர்வகிக்கவும்",
    "header.search": "வாடிக்கையாளர்கள், இன்வாய்ஸ்களைத் தேடுங்கள்...",
    "header.role": "சார்ட்டர்ட் அக்கவுண்டன்ட் (CA)",
    "header.sign_out": "வெளியேறு",

    // Settings
    "settings.title": "அமைப்புகள்",
    "settings.subtitle": "உங்கள் சுயவிவரம், பாதுகாப்பு மற்றும் விருப்பங்களை நிர்வகிக்கவும்",
    "settings.tabs.profile": "சுயவிவரம்",
    "settings.tabs.security": "பாதுகாப்பு",
    "settings.tabs.notifications": "அறிவிப்புகள்",
    "settings.tabs.preferences": "விருப்பங்கள்",

    // Profile Tab
    "profile.card_title": "சுயவிவரம்",
    "profile.card_desc": "உங்கள் தனிப்பட்ட தகவலைப் புதுப்பிக்கவும்",
    "profile.change_photo": "புகைப்படத்தை மாற்றவும்",
    "profile.remove_photo": "அகற்று",
    "profile.photo_helper": "JPG அல்லது PNG, அதிகபட்சம் 2 MB",
    "profile.first_name": "முதல் பெயர்",
    "profile.last_name": "கடைசி பெயர்",
    "profile.email": "மின்னஞ்சல்",
    "profile.membership_no": "உறுப்பினர் எண் (ICAI)",
    "profile.save_changes": "மாற்றங்களைச் சேமி",
    "profile.saving": "சேமிக்கிறது...",

    // Security Tab
    "security.card_title": "பாதுகாப்பு",
    "security.two_factor": "இரு காரணி அங்கீகாரம்",
    "security.two_factor_desc": "கூடுதல் பாதுகாப்பைச் சேர்க்கவும்",
    "security.login_alerts": "உள்நுழைவு விழிப்பூட்டல்கள்",
    "security.login_alerts_desc": "புதிய உள்நுழைவுகள் குறித்து அறிவிக்கப்படுங்கள்",
    "security.session_timeout": "அமர்வு காலாவதி",
    "security.session_timeout_desc": "செயலற்ற நிலைக்குப் பிறகு தானாக வெளியேறுதல்",
    "security.change_password": "கடவுச்சொல்லை மாற்றவும்",
    "security.change_password_desc": "உங்கள் தற்போதைய கடவுச்சொல்லை உள்ளிட்டு புதிய கடவுச்சொல்லைத் தேர்ந்தெடுக்கவும்.",
    "security.current_password": "தற்போதைய கடவுச்சொல்",
    "security.new_password": "புதிய கடவுச்சொல்",
    "security.confirm_password": "புதிய கடவுச்சொல்லை உறுதிப்படுத்தவும்",
    "security.cancel": "ரத்துசெய்",
    "security.update_password": "கடவுச்சொல்லைப் புதுப்பிக்கவும்",
    "security.updating": "புதுப்பிக்கிறது...",
    "security.min_chars": "குறைந்தது 6 எழுத்துக்கள்",
    "security.enter_current": "தற்போதைய கடவுச்சொல்லை உள்ளிடவும்",
    "security.reenter_new": "புதிய கடவுச்சொல்லை மீண்டும் உள்ளிடவும்",
    "security.password_mismatch": "கடவுச்சொற்கள் பொருந்தவில்லை",

    // Notifications Tab
    "notifications.card_title": "அறிவிப்பு விருப்பங்கள்",
    "notifications.compliance": "இணக்க காலக்கெடு",
    "notifications.compliance_desc": "GST மற்றும் வரி தாக்கல் நினைவூட்டல்கள்",
    "notifications.audit": "தணிக்கை விழிப்பூட்டல்கள்",
    "notifications.audit_desc": "மோசடி மற்றும் இடர் அறிவிப்புகள்",
    "notifications.client": "வாடிக்கையாளர் செயல்பாடு",
    "notifications.client_desc": "பதிவேற்றங்கள் மற்றும் நிலை மாற்றங்கள்",
    "notifications.product": "தயாரிப்பு புதுப்பிப்புகள்",
    "notifications.product_desc": "புதிய அம்சங்கள் மற்றும் குறிப்புகள்",

    // Preferences Tab
    "preferences.card_title": "விருப்பங்கள்",
    "preferences.language": "மொழி",
    "preferences.language_desc": "இடைமுக மொழி",
    "preferences.currency": "நாணயம்",
    "preferences.currency_desc": "இந்திய வரிவிதிப்புக்கான இயல்புநிலை நாணயம்",
    "preferences.currency_locked_desc": "இந்திய ரூபாய் (INR ₹) மட்டுமே ஆதரிக்கப்படுகிறது",
    "preferences.theme": "தீம்",
    "preferences.theme_desc": "தோற்றம்",
    "preferences.theme_dark": "இருண்ட",
    "preferences.theme_light": "வெளிச்சமான",
  },
};

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<SupportedLanguage>(() => {
    const saved = localStorage.getItem("fl_lang");
    if (saved && (saved === "en" || saved === "hi" || saved === "gu" || saved === "mr" || saved === "ta")) {
      return saved as SupportedLanguage;
    }
    return "en";
  });

  const setLanguage = (lang: SupportedLanguage) => {
    setLanguageState(lang);
    localStorage.setItem("fl_lang", lang);
    window.dispatchEvent(new CustomEvent("finledger:language-changed", { detail: lang }));
  };

  const t = (key: string): string => {
    const dict = translations[language] || translations.en;
    return dict[key] || translations.en[key] || key;
  };

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useTranslation() {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    // Fallback if rendered outside provider
    return {
      language: "en" as SupportedLanguage,
      setLanguage: () => {},
      t: (k: string) => k,
    };
  }
  return ctx;
}

export default LanguageContext;
