---
doc_id: SEC-STD-PASSWORD
title: Password Standard
version: "1.0"
effective_date: 2025-09-01
owner: Information Security
classification: internal
---

# Password Standard

## 1. Purpose

Passwords are a key part of how we protect Kranich Route Cloud, the customer data we hold, and our own internal systems. This standard explains what we expect from every employee when creating and managing passwords. It applies to all accounts used for Kranich work, whether the system is hosted by us, by a customer, or by a third-party provider.

We keep this standard simple on purpose. We know that complicated rules lead people to reuse passwords or write them down in unsafe places. This standard is built around tools that do the hard work for you — our password manager and single sign-on — so that remembering long strings of characters is rarely necessary.

This document is owned by Information Security. If you have questions after reading it, see §4.

## 2. Requirements

### 2.1 Use the password manager

Every Kranich employee has a license for 1Password, our approved password manager. You must use 1Password for all work-related accounts, with the following exceptions:

- Accounts that require a hardware security key and do not support password managers.
- Accounts where the provider explicitly forbids password managers in their terms of service. If you encounter this, contact security@kranich.example before proceeding.

When 1Password generates a password for you, it stores it securely and fills it in when you log in. You do not need to memorize these passwords. What you do need to remember is your master password for 1Password itself, plus the method you use to unlock it on your devices.

### 2.2 Creating passwords

When you create a password for a work account, follow these rules:

- Let 1Password generate the password whenever the system allows it. Generated passwords are long and random, which is what we want.
- If you must choose a password yourself, make it a passphrase of several unrelated words. The length requirement is defined in POL-005 §2; please review that document for the minimum.
- Never use a password that you have used before, for any account, personal or professional.
- Never use personal information such as your name, your pet's name, your birthday, or your address. These are easy for others to guess or find online.
- Never use patterns such as sequential keyboard keys or repeated characters.

### 2.3 Passwords are secret

Your passwords protect Kranich systems and customer data. Treat them accordingly:

- Do not share your password with anyone, including colleagues, managers, or IT support. No legitimate person will ever ask you for your password — not Information Security, not the IT helpdesk, not your manager.
- Do not write passwords on paper, in unencrypted notes, or in documents stored outside 1Password.
- Do not enter a Kranich password into a website or application that you reached through an unexpected link or that does not show the correct address in your browser.
- If you suspect that a password may have been compromised — for example, because you entered it into a suspicious page — change it promptly and report the incident to security@kranich.example.

Example: Anna, a backend engineer in Lisbon, receives an email that appears to be from her manager asking her to confirm her password for a system upgrade. She recognizes this as a phishing attempt, does not reply, and forwards the email to security@kranich.example.

### 2.4 Changing passwords

You do not need to change your passwords on a fixed schedule. Regular, forced password changes often lead people to make small, predictable variations, which actually weaken security. Instead:

- Change a password promptly if you have reason to believe it is compromised.
- Change a password when you leave a project or when someone who knew it leaves the company.
- Change your 1Password master password if you suspect someone else knows it.

### 2.5 Master password for 1Password

Your master password is the one password you must know from memory. It unlocks access to all your other credentials. Choose it carefully:

- Make it a passphrase that is easy for you to remember but hard for others to guess. Avoid famous quotes, song lyrics, or phrases that appear in public writing about you.
- Do not reuse your master password anywhere else.
- Do not store your master password in 1Password itself, in your browser, or in any digital file.
- If you forget your master password, you will need to go through account recovery. This takes time, so treat your master password with care.

### 2.6 Avoiding reuse

Password reuse is one of the most common ways accounts get compromised. If a password appears in a data breach on one service, attackers will try it on many other services. Because you use 1Password for work accounts, every account can have its own unique password without any extra effort on your part.

For personal accounts, we encourage you to use a personal password manager with the same habit of unique passwords. This protects you personally and also reduces the risk that a personal breach gives someone access to work systems.

## 3. Managers and vaults

### 3.1 What belongs in 1Password

Store the following in 1Password:

- Passwords for all work-related websites and applications.
- Passwords for shared service accounts that your team uses.
- API keys, tokens, and other secrets that your role requires you to handle, unless a more specific standard applies.
- Answers to security questions for work accounts. Treat these as passwords: generate random answers and store them in 1Password rather than providing truthful, guessable answers.

Do not store:

- Your 1Password master password.
- Personal passwords that are unrelated to work, unless you use a separate personal vault within 1Password for this purpose. If you do keep personal items in 1Password, keep them clearly separated from work items.

### 3.2 Vault structure

1Password organizes items into vaults. Use the vaults that your team or Information Security has set up for you. As a general guide:

- Your private vault is for credentials that only you use.
- Shared vaults are for credentials that multiple people need. Only add credentials to a shared vault when more than one person genuinely needs them.
- When someone leaves a team or the company, People & Culture coordinates with Information Security to review vault access and remove people who no longer need it.

Example: Deniz, a customer success manager in Berlin, keeps her own login for the customer portal in her private vault. Her team shares a login for a demo environment in a shared vault so that anyone on the team can run a demonstration when needed.

### 3.3 Service accounts

Some systems use service accounts that are not tied to a single person. These accounts often have elevated access and need extra care:

- Store service account passwords in a shared vault that only the people who operate the system can access.
- Rotate service account passwords when someone with access leaves the company or changes roles.
- Prefer technical solutions such as short-lived tokens or key-based authentication over long-lived passwords wherever the system supports it.

If you manage a service account, review its access list regularly and remove people who no longer need it. If you are unsure who has access, contact security@kranich.example.

### 3.4 Multi-factor authentication

Where a system supports multi-factor authentication, you must enable it. This is not strictly a password rule, but it is closely related: a stolen password alone should not be enough to access a Kranich system. Your manager or the system owner can tell you which authentication methods are approved for each system. If you lose your authentication device, contact it-help@kranich.example promptly so that recovery can happen in a controlled way.

## 4. Questions

If you have questions about this standard, start with your manager or your team lead. They can often answer routine questions or point you to the right resource.

For questions about specific systems, contact it-help@kranich.example.

For questions about security incidents, suspected compromises, or whether a particular practice is acceptable under this standard, contact security@kranich.example.

For questions about how this standard relates to your employment or to team processes, contact people@kranich.example.

We review this standard periodically. If you have suggestions for making it clearer or easier to follow, send them to security@kranich.example. We would rather hear from you than have you quietly struggle with a rule that does not make sense in practice.

Example: Marek, a field solutions engineer working with clients in Poland, is setting up a new client demo environment. The client requires a password that meets their own policy, which differs from ours. He checks whether the client system supports integration with our single sign-on. When it does not, he stores the credential in a shared vault and notes the client-specific requirement in the vault item so that colleagues who use the account later understand why the password looks different from our usual standard.

Example: Sofia, a product manager in the Fleet Insights team working remotely from Spain, receives a notification from 1Password that one of her stored credentials may have appeared in a data breach. She follows the prompt to change that password immediately and also reviews her other accounts for any that use a similar password. She then mentions the incident to her manager during their next check-in, and her manager confirms that no further action is needed beyond what she already did.

Remember that the goal of this standard is not to make your work harder. It is to make sure that a single mistake — a reused password, a phishing link, a lost device — does not become a way into Kranich systems or our customers' data. Following these rules, and using the tools we provide, keeps that risk low while letting you focus on your work.
