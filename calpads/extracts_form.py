"""Extract form handler"""


class ExtractsForm:

    def __init__(self, form_root):
        """Takes in the lxml.etree.fromstring() root of the form"""
        self.root = form_root
        self.named_fields = [tag for tag in self.root.xpath('.//*[@name]')]
        self.prefilled_fields = [(field.attrib['name'], field.attrib.get('value'))
                                 for field in self.named_fields]

    def get_parsed_form_fields(self):
        all_parsed_options = dict()
        all_parsed_options.update(self.find_text_inputs())
        all_parsed_options.update(self.find_checkboxes())
        all_parsed_options.update(self.find_selects_no_multiple())
        all_parsed_options.update(self.find_selects_allow_multiple())

        return all_parsed_options

    def find_text_inputs(self):
        text_inputs = [tag for tag in self.named_fields
                      if tag.tag == 'input'
                      and tag.attrib.get('type') == 'text'
                      and tag.attrib['name'] != 'RecordType']
        non_date_options = [(tag.attrib['name'], str)
                            for tag in text_inputs
                            if 'date' not in tag.attrib['name'].lower()]
        date_options = [(tag.attrib['name'],
                             'string with valid date formatting, MM/DD/YYYY e.g. 02/02/2020')
                            for tag in text_inputs
                            if 'date' in tag.attrib['name'].lower()]
        return dict(non_date_options + date_options)

    def find_checkboxes(self):
        checkboxes = [tag for tag in self.named_fields
                      if tag.tag == 'input'
                      and tag.attrib.get('type') == 'checkbox']
        options = [(tag.attrib['name'], bool) for tag in checkboxes]
        return dict(options)

    def find_selects_allow_multiple(self):
        multiple = [tag for tag in self.named_fields if tag.attrib.get('multiple')]
        return self._scrape_options_to_dict(multiple, True)

    def find_selects_no_multiple(self):
        selects_no_mult = [tag for tag in self.named_fields
                           if not tag.attrib.get('multiple')
                           and tag.tag == 'select'
                           and tag.attrib['name'] != 'ReportingLEA']
        return self._scrape_options_to_dict(selects_no_mult, False)

    def _scrape_options_to_dict(self, selects, allow_multiple=True):
        options_dict = dict()
        for tag in selects:
            options = [(option.text, option.attrib.get('value'))
                       for option in tag.xpath('.//option')]
            options_dict[tag.attrib['name']] = dict([('_allows_multiple', allow_multiple)] + options)

        return options_dict


