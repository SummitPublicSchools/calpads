# Why embark on this experiment?
I have done a bit of work on a Selenium-based automation framework for CALPADS. It's mostly functional but has recently come across some limitations. I was able to work on a potential workaround for the limitation by falling back to the Python `requests` module. Some of the few problems I would like to address with this experimentation:
- **Headless downloading**: I wanted to run some downloads on a headless chromedriver in a containerized Airflow environment, but the Reports functionality within CALPADS was unable to download the reports with a high level of consistency.
- **Selenium errors**: Occasionally, the Selenium-based automation errors out with a `StaleElementException` or some other exception but when once runs it again, it runs without issues. It needs some fine tuning to make it more robust.
- **Automated, but slow**: The Selenium automation saves time, but can still be a time-suck especially when errors occur.
- **CALPADS has stateful links, and I want to use them**: The state system actually has quite a few direct access "endpoints". We can provide that alongside a Selenium based API, but it makes more sense as part of a grander Web API wrapper solution.

# This is cool and all, but guaranteed to be time consuming. What does success look like?
I'm a firm believer in learning for learning's sake, particularly when it comes to programming. I have already learned quite a bit in dipping my toe at whether this might be feasible, I will certainly learn much more by diving in. However, I am also driven by a desire to have a reliable end-to-end framework for state reporting. That is:

1) _**Student Information System**_ *>>* _**Human Intervention**_ *>>* _**CALPADS**_

2) _**CALPADS**_ *>>* _**Human Intervention**_ *>>* _**Student Information System**_

A seamless cyclical approach to maintaining data quality in two+ systems. I'll write a blog post to say more about this, but essentially I'd like to experiment more with an "Airflow, but for like, non-scheduled, irregular workflows". I'm thinking somewhere along the lines of Dagster's on-the-fly execution configuration changes.
