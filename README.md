# calpads
An experimental and unofficial Python Web API wrapper for California Department of Education CALPADS.

[Version 0.3.0](https://github.com/yo-my-bard/calpads/tree/0.3.0) is pretty great and covers many use-cases. Given its lack of official support, the wrapper is subject to break at any moment if the internals of CALPADS magic change hence why we remain experimental. Also, we're still experimenting.

# Supported Endpoints
* `Leas` - lists all(?) Leas
* A number of `/Students` endpoints are currently functional. These are the famous individual sub-sections on the student page, but delivered in JSON with ⚡️ speed

# Features
* `Reports` downloads for reports with an expressive API that exposes most form fields
* `Extracts` downloads for most extracts with an expressive API to support many requesting "modes" (e.g. by date range)
* Supports switching between multiple LEAs

# Installation
* To get much of this speed gain, we depend on `lxml`. They have specific [installation instructions here](https://lxml.de/installation.html).
* Recommend pip: `pip install git+https://github.com/SummitPublicSchools/calpads.git@0.3.0`

# Planned Experimentations
* Extract/File Upload operations
