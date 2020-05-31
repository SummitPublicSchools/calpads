"""Extract form handler"""
import logging

class ExtractsForm:

    def __init__(self, form_root):
        """Takes in the root form node returned by lxml.etree.fromstring()"""
        self.root = form_root
        self.named_fields = [tag for tag in self.root.xpath('.//*[@name]')]
        self.prefilled_fields = [(field.attrib['name'], field.attrib.get('value'))
                                 for field in self.named_fields]
        self.log = logging.getLogger(__name__)
        log_fmt = f'%(levelname)s: %(asctime)s {self.__class__.__name__}.%(funcName)s: %(message)s'
        stream_hdlr = logging.StreamHandler()
        stream_hdlr.setFormatter(logging.Formatter(fmt=log_fmt))
        self.log.addHandler(stream_hdlr)

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
        non_date_options = [(tag.attrib['name'],
                             {'Required': 'data-val-required' in tag.attrib,
                              'ValidValues': str})
                            for tag in text_inputs
                            if 'date' not in tag.attrib['name'].lower()]
        date_options = [(tag.attrib['name'],
                         {'Required': 'data-val-required' in tag.attrib,
                          'ValidValues': 'string with valid date formatting, MM/DD/YYYY e.g. 02/02/2020'})
                            for tag in text_inputs
                            if 'date' in tag.attrib['name'].lower()]
        return dict(non_date_options + date_options)

    def find_checkboxes(self):
        checkboxes = [tag for tag in self.named_fields
                      if tag.tag == 'input'
                      and tag.attrib.get('type') == 'checkbox']
        options = [(tag.attrib['name'],
                    {'Required': 'data-val-required' in tag.attrib,
                     'ValidValues': bool})
                   for tag in checkboxes]
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

    def _filter_text_input_fields(self, form_data_tuple):
        all_text_inputs = self.find_text_inputs()
        all_form_keys = [field[0] for field in form_data_tuple]

        inputs_to_add = []

        for key_idx, key in enumerate(all_form_keys):
            if key not in all_text_inputs.keys():
                inputs_to_add.append(form_data_tuple[key_idx])

        for key in all_text_inputs.keys():
            #self.log.debug('Checking Key {}'.format(key))
            for key2 in all_form_keys:
                if key == key2:
                    #self.log.debug('Key in form input {} found in parser'.format(key2))
                    if all_form_keys.count(key2) > 1:
                        #self.log.debug('Key {} has duplicates submitted. Selecting the last one.'.format(key2))
                        #This math is still trippy to me @_@
                        #https://stackoverflow.com/a/522401
                        idx = len(all_form_keys) - all_form_keys[::-1].index(key) - 1
                        inputs_to_add.append(form_data_tuple[idx])
                        # self.log.debug('At this idx {}, found {} in original. In keys, it is {}'
                        #                .format(idx, form_data_tuple[idx], all_form_keys[idx]))
                        # self.log.debug('Moving on to a new key from {}'.format(key2))
                        break
                    else:
                        # self.log.debug('Key {} does not appear to have duplicates'.format(key2))
                        idx = all_form_keys.index(key2)
                        inputs_to_add.append(form_data_tuple[idx])
                        # self.log.debug('Moving on to a new key from {}'.format(key2))
                        break

        return inputs_to_add

    def _scrape_options_to_dict(self, selects, allow_multiple=True):
        options_dict = dict()
        for tag in selects:
            options = [(option.text, option.attrib.get('value'))
                       for option in tag.xpath('.//option')]
            options_dict[tag.attrib['name']] = {'Required': 'data-val-required' in tag.attrib,
                                                'ValidValues': dict([('_allows_multiple', allow_multiple)] + options)}

        return options_dict