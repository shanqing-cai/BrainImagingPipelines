import os
import nipype.pipeline.engine as pe
import nipype.interfaces.utility as util
import nipype.interfaces.io as nio
import argparse
import sys
from reportsink.io import ReportSink

addtitle = lambda x: "Resting_State_Correlations_fwhm%s"%str(x)

def start_config_table():
    import numpy as np
    param_names = np.asarray(['motion', 'composite norm', 'compcorr components', 'outliers', 'motion derivatives'])
    boolparams=np.asarray(c.reg_params)
    params = param_names[boolparams]
    table = []
    table.append(['TR',str(c.TR)])
    table.append(['Slice Order',str(c.SliceOrder)])
    table.append(['Interleaved',str(c.Interleaved)])
    if c.use_fieldmap:
        table.append(['Echo Spacing',str(c.echospacing)])
        table.append(['Fieldmap Smoothing',str(c.sigma)])
        table.append(['TE difference',str(c.TE_diff)])
    table.append(['Art: norm thresh',str(c.norm_thresh)])
    table.append(['Art: z thresh',str(c.z_thresh)])
    table.append(['fwhm',str(c.fwhm)])    
    table.append(['highpass freq',str(c.highpass_freq)])
    table.append(['lowpass freq',str(c.lowpass_freq)])
    table.append(['Regressors',str(params)])
    return [[table]]

def corr_image(resting_image,fwhm):
    """This function makes correlation image on brain surface"""
    import numpy as np
    import nibabel as nb
    import matplotlib.pyplot as plt
    from surfer import Brain, Surface
    import os
    
    img = nb.load(resting_image)
    corrmat = np.corrcoef(np.squeeze(img.get_data()))
    corrmat[np.isnan(corrmat)] = 0
    br = Brain('fsaverage5', 'lh', 'smoothwm')

    #br.add_overlay(corrmat[0,:], min=0.2, name=0, visible=True)
    values = nb.freesurfer.read_annot('/software/Freesurfer/5.1.0/subjects/fsaverage5/label/lh.aparc.annot')

    #br.add_overlay(np.mean(corrmat[values[0]==5,:], axis=0), min=0.8, name='mean', visible=True)
    
    
    data = img.get_data()

    data = np.squeeze(img.get_data())
    
    #
    precuneus_signal = np.mean(data[values[0]==np.nonzero(np.array(values[2])=='precuneus')[0][0],:], axis=0)
    precuneus = np.corrcoef(precuneus_signal, data)
    #precuneus.shape
    
    #br.add_overlay(precuneus[0,1:], min=0.3, sign='pos', name='mean', visible=True)

    br.add_overlay(precuneus[0,1:], min=0.2, name='mean', visible=True)
    plt.hist(precuneus[0,1:], 128)
    plt.savefig(os.path.abspath("histogram.png"))
    plt.close()
    
    corr_image = os.path.abspath("corr_image%s.png"%fwhm)
    br.save_montage(corr_image)
    ims = br.save_imageset(prefix=os.path.abspath('fwhm_%s'%str(fwhm)),views=['medial','lateral','caudal','rostral','dorsal','ventral'])
    br.close()
    print ims
    #precuneus[np.isnan(precuneus)] = 0
    #plt.hist(precuneus[0,1:])
    
    roitable = [['Region','Mean Correlation']]
    for i, roi in enumerate(np.unique(values[2])):
        roitable.append([roi,np.mean(precuneus[values[0]==np.nonzero(np.array(values[2])==roi)[0][0]])])    
    
    #images = [corr_image]+ims+[os.path.abspath("histogram.png"), roitable]
    roitable=[roitable]
    histogram = os.path.abspath("histogram.png")
    
    return corr_image, ims, roitable, histogram
    
def vol2surf(input_volume,ref_volume,reg_file,trg,hemi):
    import os
    out_file = os.path.abspath("surface.nii")
    os.system("mri_vol2surf --mov %s --ref %s --reg %s --trgsubject %s \
              --hemi %s --out_type nii --out %s --interp trilinear \
              --projfrac 0.5" % (input_volume, ref_volume, reg_file,
                                  trg, hemi, out_file))
    return out_file

def resting_datagrab(name="resting_datagrabber"):
    datasource = pe.Node(interface=nio.DataGrabber(infields=['subject_id',
                                                             'fwhm'],
                                                   outfields=['reg_file',
                                                              'mean_image',
                                                              "mask",
                                                              "func"]),
                         name = name)
    datasource.inputs.base_directory = os.path.join(c.sink_dir,'analyses','func')
    datasource.inputs.template ='*'
    datasource.inputs.field_template = dict(reg_file='%s/preproc/bbreg/*.dat',
                                            mean_image='%s/preproc/mean/*.nii.gz',
                                            mask='%s/preproc/mask/*_brainmask.nii',
                                            func="%s/preproc/output/fwhm_%s/%s_r??_bandpassed.nii.gz")
    datasource.inputs.template_args = dict(reg_file=[['subject_id']],
                                           mean_image=[['subject_id']],
                                           mask=[['subject_id']],
                                           func=[['subject_id','fwhm','subject_id']])
    return datasource

def resting_QA(name="resting_QA"):
    
    workflow=pe.Workflow(name=name)
    inputspec = pe.Node(interface=util.IdentityInterface(fields=["in_files",
                                                                 "reg_file",
                                                                 "subjects_dir",
                                                                 "mean_image"]), name="inputspec")
    infosource = pe.Node(util.IdentityInterface(fields=['subject_id']),
                         name='subject_names')
    infosource.iterables = ('subject_id', c.subjects)
    
    fwhmsource = pe.Node(util.IdentityInterface(fields=['fwhm']),
                         name='fwhm_source')
    fwhmsource.iterables = ('fwhm',c.fwhm)
    dataflow = resting_datagrab()
    #dataflow.inputs.fwhm = c.fwhm
    workflow.connect(fwhmsource,'fwhm',dataflow,'fwhm')
    workflow.connect(infosource,'subject_id',dataflow,'subject_id')
    workflow.connect(dataflow,'func', inputspec,'in_files')
    workflow.connect(dataflow,'reg_file', inputspec, 'reg_file')
    workflow.inputs.inputspec.subjects_dir = c.surf_dir
    workflow.connect(dataflow,'mean_image', inputspec,'mean_image')
    
    tosurf = pe.MapNode(util.Function(input_names=['input_volume',
                                                'ref_volume',
                                                'reg_file',
                                                'trg',
                                                'hemi'],
                                   output_names=["out_file"],
                                   function=vol2surf), name='vol2surf',iterfield=["input_volume"])
    tosurf.inputs.hemi = 'lh'
    tosurf.inputs.trg = 'fsaverage5'
    
    workflow.connect(inputspec,'in_files',tosurf,'input_volume')
    workflow.connect(inputspec,'reg_file',tosurf,'reg_file')
    workflow.connect(inputspec,'mean_image', tosurf,'ref_volume')
    
    to_img = pe.MapNode(util.Function(input_names=['resting_image','fwhm'],
                                   output_names=["corr_image","ims","roitable","histogram"],function=corr_image),
                     name="image_gen",iterfield=["resting_image"])
                     
    workflow.connect(tosurf,'out_file',to_img,'resting_image')
    workflow.connect(fwhmsource,'fwhm',to_img,'fwhm')
    #to_img.inputs.fwhm = c.fwhm
    
    sink = pe.Node(ReportSink(orderfields=["Introduction","Subject","Configuration","Correlation_Images","Other_Views","ROI_Table","Histogram"]),name="write_report")
    sink.inputs.base_directory = os.path.join(c.sink_dir,'analyses','func')
    sink.inputs.json_sink = c.json_sink
    sink.inputs.Introduction = "Resting state corellations with seed at precuneus"
    sink.inputs.Configuration = start_config_table()
    #sink.inputs.report_name = "Resting_State_Correlations"
    workflow.connect(infosource,'subject_id',sink,'Subject')
    workflow.connect(fwhmsource,('fwhm',addtitle),sink,'report_name')
    workflow.connect(infosource,'subject_id',sink,'container')
    workflow.connect(to_img,"corr_image",sink,"Correlation_Images")
    workflow.connect(to_img,"ims",sink,"Other_Views")
    workflow.connect(to_img,"roitable",sink,"ROI_Table")
    workflow.connect(to_img,"histogram",sink,"Histogram")
    
    
    
    return workflow
    
if __name__== "__main__":
    
    parser = argparse.ArgumentParser(description="example: \
                        run resting_preproc.py -c config.py")
    parser.add_argument('-c','--config',
                        dest='config',
                        required=True,
                        help='location of config file'
                        )
    args = parser.parse_args()
    path, fname = os.path.split(os.path.realpath(args.config))
    sys.path.append(path)
    c = __import__(fname.split('.')[0])
    
    a = resting_QA()
    a.base_dir = c.working_dir
    a.write_graph()
    
    if not os.environ['SUBJECTS_DIR'] == c.surf_dir:
        print "Your SUBJECTS_DIR is incorrect!"
        print "export SUBJECTS_DIR=%s"%c.surf_dir
    else:
        if c.run_on_grid:
            a.run(plugin=c.plugin,plugin_args=c.plugin_args)
        else:
            a.run()
    
    
"""    
--mov input volume path (or --src)
   --ref reference volume name (default=orig.mgz
   --reg source registration  
   --regheader subject
   --mni152reg : $FREESURFER_HOME/average/mni152.register.dat
   --rot   Ax Ay Az : rotation angles (deg) to apply to reg matrix
   --trans Tx Ty Tz : translation (mm) to apply to reg matrix
   --float2int float-to-int conversion method (<round>, tkregister )
   --fixtkreg : make make registration matrix round-compatible
   --fwhm fwhm : smooth input volume (mm)
   --surf-fwhm fwhm : smooth output surface (mm)

   --trgsubject target subject (if different than reg)
   --hemi       hemisphere (lh or rh) 
   --surf       target surface (white) 
   --srcsubject source subject (override that in reg)

 Options for use with --trgsubject
   --surfreg    surface registration (sphere.reg)  
   --icoorder   order of icosahedron when trgsubject=ico

 Options for projecting along the surface normal:
   --projfrac frac : (0->1)fractional projection along normal 
   --projfrac-avg min max del : average along normal
   --projfrac-max min max del : max along normal
   --projdist mmdist : distance projection along normal 
   --projdist-avg min max del : average along normal
   --projopt <fraction stem> : use optimal linear estimation and previously
computed volume fractions (see mri_compute_volume_fractions)
   --projdist-max min max del : max along normal
   --mask label : mask the output with the given label file (usually cortex)
   --cortex : use hemi.cortex.label from trgsubject

 Options for output
   --o         output path
   --out_type  output format
   --frame   nth :  save only 0-based nth frame 
   --noreshape do not save output as multiple 'slices'
   --rf R  integer reshaping factor, save as R 'slices'
   --srchit   volume to store the number of hits at each vox 
   --srchit_type  source hit volume format 
   --nvox nvoxfile : write number of voxels intersecting surface

 Other Options
   --reshape : so dims fit in nifti or analyze
   --noreshape : do not reshape (default)
   --scale scale : multiply all intensities by scale.
   --v vertex no : debug mapping of vertex.
   --srcsynth seed : synthesize source volume
   --seedfile fname : save synth seed to fname
   --sd SUBJECTS_DIR 
   --help      print out information on how to use this program
   --version   print out version and exit

   --interp    interpolation method (<nearest> or trilinear)
"""
