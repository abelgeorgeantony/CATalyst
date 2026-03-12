# CATalyst
This project aims to be a practice ground for me to get a good rank in CUSAT CAT(MCA).

Will I become a laughing stock for doing crazy things like this and still not getting into cusat? Only time will tell... The worst case that can happen when you do something improbable is the same as if you hadn't done anything, but the best case might surprise you!

To add custom questions and answers that are not currently in this:\
If trying to add a previous year question paper officially provided by CUSAT, you first need to convert the pdf into a suitable form/structure for the application to use, refer (the JSON schema)[./assets/data/db_schema.json]. You should also take a look at the already (existing data)[./assets/data/json/].\
I have already provided some python scripts that will help in converting the pdfs to the JSON structure.  Still human analysis is required to maintian the robustness of the data. If the content/text in the pdf is not interactable/selectable or if the content is of low quality then the scripts are of no use to you. You must use OCR to extract the text content.\
