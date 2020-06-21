# calpads
An unofficial Python Web API wrapper for California Department of Education's CALPADS.

[Version 0.5.0](https://github.com/yo-my-bard/calpads/tree/0.5.0) is pretty great and covers many use-cases. Given its lack of official support, the wrapper is subject to break at any moment if the internals of CALPADS magic change.

# We Have Documentation!
Supported endpoints, downloads, and other features are [documented in our GitBook website](https://summit-public-schools.gitbook.io/calpads-api/).
Here are some of our favorite highlights:
* A number of `/Students` endpoints are currently functional. These are the famous individual sub-sections on the student page, but delivered in JSON with ⚡️ speed
* `Reports` downloads for reports with an expressive API that exposes most form fields
* `Extracts` downloads for most extracts with an expressive API to support many requesting "modes" (e.g. by date range)
* Supports switching between multiple LEAs
* Supports uploading *and* posting files
* Supports fetching file upload errors (using the `Extracts` downloads)

# Installation
* To get much of this speed gain, we depend on `lxml`. They have specific [installation instructions here](https://lxml.de/installation.html).
* Recommend pip: `pip install git+https://github.com/SummitPublicSchools/calpads.git@0.5.0`