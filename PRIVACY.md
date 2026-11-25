# Privacy Policy

**OSINT Watcher** — last updated October 29, 2026

This application is a personal automation tool. It is operated by and for a
single individual user (the account owner) and is not offered as a public
service. It has no other users and no public sign-up.

## What it accesses

With the account owner's explicit authorization, the application accesses the
following Google services **for the account owner's own account only**:

| Service | Scope | Purpose |
|---|---|---|
| Gmail | `gmail.readonly`, `gmail.send`, `gmail.modify` | Search the owner's own mailbox for newsletter subscriptions, and send a daily news digest to the owner's own address |
| Google Calendar | `calendar` | Read the owner's own calendar (optional features) |
| Google Drive | `drive` | Store archive files in the owner's own Drive (optional features) |
| Contacts | `contacts.readonly` | Read the owner's own contact list (optional features) |
| Sheets | `spreadsheets` | Read and write the owner's own spreadsheets (optional features) |
| Docs | `documents` | Create and edit the owner's own documents (optional features) |

Access is limited to data belonging to the authorizing account. The
application does not and cannot access any other person's Google data.

## What is stored and where

OAuth credentials (an access token and refresh token) are stored locally on the
owner's own computer at `~/.hermes/google_token.json` with file permissions
restricted to the owner. No credentials are transmitted to or stored on any
third-party server operated by this application.

Retrieved email content is processed locally to produce a news digest and is
not retained beyond what is needed to generate that digest. Digest archives are
stored locally and may be committed to the owner's own private repositories.

## What is shared

Nothing. Message content, contact data, and credentials are never sold, rented,
shared, or disclosed to any third party. No data is used for advertising,
profiling, or training machine-learning models.

Generating the digest requires sending email subject lines and article text to
a third-party large language model provider (currently OpenRouter or OpenAI) for
summarisation. This is limited to the content of publicly published news
articles and newsletter headlines, and is disclosed here for completeness.

## Data retention and deletion

Locally stored data can be deleted by the owner at any time by removing the
relevant local files. The refresh token can be revoked at any time at
https://myaccount.google.com/permissions, which immediately and permanently
ends the application's access.

## Limited Use disclosure

The application's use of information received from Google APIs adheres to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements. Specifically:

- Data is used only to provide the digest feature described above.
- Data is not transferred to third parties except as required to provide that
  feature, for security purposes, or to comply with law.
- Data is not used for advertising.
- No humans read the data, other than the account owner.

## Contact

Questions about this policy: jesjohannesen@gmail.com
